#!/usr/bin/env python3
"""Video Factory: script -> voiceover + stock footage + captions -> MP4.

Script format (see scripts/script.txt):
    ## english keywords for footage
    Narration text for this scene (any language).

Requires: ffmpeg, edge-tts, requests, and PEXELS_API_KEY (free).
Set DRY_RUN=1 to test the pipeline with fake audio/video (no internet).
"""
import argparse
import asyncio
import math
import os
import random
import re
import subprocess
import sys
from pathlib import Path

DRY = os.environ.get("DRY_RUN") == "1"
SEG = 8.0  # seconds per footage clip inside a scene
TAIL = 0.35  # silence after each scene


def run(cmd, cwd=None):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit("ffmpeg/command failed:\n" + " ".join(map(str, cmd)) + "\n" + p.stderr[-1500:])
    return p.stdout


def parse_script(path):
    scenes, kw, buf = [], None, []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("##"):
            if buf:
                scenes.append((kw or "nature", " ".join(buf)))
                buf = []
            kw = s.lstrip("#").strip()
        elif s and not s.startswith("#"):
            buf.append(s)
    if buf:
        scenes.append((kw or "nature", " ".join(buf)))
    if not scenes:
        sys.exit("السكريبت فاضي. اكتب مشاهد بالشكل: ## keywords ثم النص.")
    return scenes


def duration(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "csv=p=0", str(path)])
    return float(out.strip())


# ---------------------------------------------------------------- audio
async def _tts(text, voice, rate, out):
    import edge_tts
    await edge_tts.Communicate(text, voice, rate=rate).save(str(out))


def make_audio(text, voice, rate, out_base):
    if DRY:
        out = out_base.with_suffix(".wav")
        d = max(2.0, len(text.split()) * 0.38)
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=220:duration={d}", str(out)])
        return out
    out = out_base.with_suffix(".mp3")
    last = None
    for attempt in range(3):
        try:
            asyncio.run(_tts(text, voice, rate, out))
            if out.exists() and out.stat().st_size > 0:
                return out
        except Exception as e:  # network / service errors
            last = e
    sys.exit(f"فشل توليد الصوت (edge-tts): {last}\n"
             "لو بيحصل على GitHub جرّب تشغّل المشروع على جهازك.")


# ---------------------------------------------------------------- footage
def pexels_clips(query, landscape, key, cache):
    import requests
    r = requests.get("https://api.pexels.com/videos/search",
                     headers={"Authorization": key},
                     params={"query": query,
                             "orientation": "landscape" if landscape else "portrait",
                             "per_page": 15}, timeout=30)
    r.raise_for_status()
    paths = []
    for v in r.json().get("videos", []):
        files = [f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4"]
        if not files:
            continue
        best = min(files, key=lambda f: abs(max(f.get("width", 0), f.get("height", 0)) - 1920))
        p = cache / f"{v['id']}.mp4"
        if not p.exists():
            data = requests.get(best["link"], timeout=120)
            data.raise_for_status()
            p.write_bytes(data.content)
        paths.append(p)
        if len(paths) >= 6:
            break
    return paths


def get_clips(query, landscape, key, cache):
    clips = pexels_clips(query, landscape, key, cache)
    if not clips:
        print(f"  ما لقيتش نتايج لـ '{query}' - هستخدم nature")
        clips = pexels_clips("nature", landscape, key, cache)
    if not clips:
        sys.exit("Pexels ما رجّعش مقاطع. اتأكد من المفتاح.")
    return clips


# ---------------------------------------------------------------- build
def build_scene(i, audio, clips, W, H, tmp):
    adur = duration(audio)
    dur = adur + TAIL
    n = max(1, round(dur / SEG))
    seglen = dur / n
    parts = []
    for j in range(n):
        part = tmp / f"s{i}_{j}.mp4"
        enc = ["-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
               "-pix_fmt", "yuv420p", str(part)]
        if DRY:
            color = "%06x" % random.randint(0x202020, 0xB0B0B0)
            run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0x{color}:s={W}x{H}:r=30",
                 "-t", f"{seglen:.3f}"] + enc)
        else:
            clip = clips[(i + j) % len(clips)]
            vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                  f"crop={W}:{H},fps=30,setsar=1")
            run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(clip),
                 "-t", f"{seglen:.3f}", "-vf", vf] + enc)
        parts.append(part)
    lst = tmp / f"s{i}.txt"
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in parts))
    scene = tmp / f"scene{i}.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(audio),
         "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-af", "apad", "-ac", "2",
         "-ar", "44100", "-c:a", "aac", "-b:a", "192k", "-t", f"{dur:.3f}", str(scene)])
    return scene, adur, duration(scene)


def srt_time(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def chunk_words(text, max_words=6):
    words = text.split()
    return [" ".join(words[k:k + max_words]) for k in range(0, len(words), max_words)]


def build_srt(entries):
    """entries: list of (offset, audio_duration, text)."""
    lines, idx = [], 1
    for offset, adur, text in entries:
        chunks = chunk_words(text)
        total = sum(len(c) for c in chunks) or 1
        t = offset
        for c in chunks:
            d = adur * len(c) / total
            lines += [str(idx), f"{srt_time(t)} --> {srt_time(t + d)}", c, ""]
            idx += 1
            t += d
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", default="scripts/script.txt")
    ap.add_argument("--mode", choices=["long", "short"], default="long")
    ap.add_argument("--voice", default="ar-EG-SalmaNeural")
    ap.add_argument("--rate", default="+0%", help="سرعة الصوت مثل +10% أو -5%")
    ap.add_argument("--out", default="out")
    ap.add_argument("--no-captions", action="store_true")
    ap.add_argument("--music", default="music.mp3", help="موسيقى خلفية اختيارية")
    a = ap.parse_args()

    landscape = a.mode == "long"
    W, H = (1920, 1080) if landscape else (1080, 1920)
    key = os.environ.get("PEXELS_API_KEY", "")
    if not key and not DRY:
        sys.exit("ضيف PEXELS_API_KEY (مفتاح مجاني من pexels.com/api).")

    out = Path(a.out)
    tmp = out / "tmp"
    cache = out / "clips"
    for d in (out, tmp, cache):
        d.mkdir(parents=True, exist_ok=True)

    scenes = parse_script(a.script)
    print(f"{len(scenes)} مشهد - الوضع: {a.mode} ({W}x{H})")

    scene_files, entries, offset = [], [], 0.0
    for i, (kw, text) in enumerate(scenes):
        print(f"مشهد {i + 1}/{len(scenes)}: {kw}")
        audio = make_audio(text, a.voice, a.rate, tmp / f"a{i}")
        clips = [] if DRY else get_clips(kw, landscape, key, cache)
        scene, adur, total = build_scene(i, audio, clips, W, H, tmp)
        scene_files.append(scene)
        entries.append((offset, adur, text))
        offset += total

    lst = tmp / "all.txt"
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in scene_files))
    merged = tmp / "merged.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(merged)])

    final = out / "video.mp4"
    use_music = Path(a.music).exists()
    use_caps = not a.no_captions
    if use_caps:
        (out / "captions.srt").write_text(build_srt(entries), encoding="utf-8")

    # libass scales SRT styles to a 288-unit-high canvas, so these are small numbers
    size, margin = (16, 25) if landscape else (12, 40)
    style = (f"FontName=Noto Sans Arabic,FontSize={size},Bold=1,PrimaryColour=&H00FFFFFF,"
             f"OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0,"
             f"Alignment=2,MarginV={margin}")
    cmd = ["ffmpeg", "-y", "-i", str(merged.resolve())]
    fc, vmap, amap = [], "0:v", "0:a"
    if use_caps:
        fc.append(f"[0:v]subtitles=captions.srt:force_style='{style}'[v]")
        vmap = "[v]"
    if use_music:
        cmd += ["-stream_loop", "-1", "-i", str(Path(a.music).resolve())]
        fc.append("[1:a]volume=0.08[m];[0:a][m]amix=inputs=2:duration=first:"
                  "dropout_transition=0[a]")
        amap = "[a]"
    if fc:
        cmd += ["-filter_complex", ";".join(fc)]
    cmd += ["-map", vmap, "-map", amap, "-c:v", "libx264", "-preset", "medium",
            "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-movflags", "+faststart", "video.mp4"]
    run(cmd, cwd=out)
    print(f"تم: {final} ({duration(final):.0f} ثانية)")


if __name__ == "__main__":
    main()
