# مصنع الفيديوهات (مجاني)

بتكتب سكريبت، وGitHub يطلعلك فيديو جاهز: صوت + مقاطع ستوك + ترجمة. طويل أو قصير.

## الإعداد (مرة واحدة)

1. اعمل حساب على github.com واعمل Repository جديد (Public أحسن عشان دقايق التشغيل المجانية).
2. ارفع كل ملفات المشروع ده فيه (Add file > Upload files). تأكد إن فولدر `.github` اترفع.
3. هات مفتاح Pexels المجاني من https://www.pexels.com/api
4. في الريبو: Settings > Secrets and variables > Actions > New repository secret
   - الاسم: `PEXELS_API_KEY`
   - القيمة: المفتاح بتاعك

## الاستخدام (كل فيديو)

1. افتح `scripts/script.txt` واكتب مشاهدك بالشكل ده:

```
## ocean waves sunset
نص المشهد اللي هيتقال بالصوت.

## deep sea fish
نص المشهد التاني.
```

السطر اللي بيبدأ بـ `##` هو **كلمات بحث إنجليزية** لمقاطع الفيديو. النص تحته بأي لغة.

2. من تاب **Actions** اختار **Make video** ثم **Run workflow**.
3. اختار `long` (أفقي 16:9 لليوتيوب) أو `short` (رأسي 9:16 للـ Shorts)، واختار الصوت.
4. استنى بضع دقايق، افتح التشغيل واحمّل الملف من **Artifacts** (اسمه video). جواه `video.mp4` و`captions.srt`.

## أصوات جاهزة

- `ar-EG-SalmaNeural` (مصري أنثى)
- `ar-EG-ShakirNeural` (مصري ذكر)
- `ar-SA-HamedNeural` (سعودي)
- `en-US-AndrewNeural` / `en-US-AriaNeural` (إنجليزي)

## موسيقى خلفية (اختياري)

ضيف ملف `music.mp3` في أول الريبو (من YouTube Audio Library مثلًا) وهيتدمج بصوت هادي.

## لو الصوت فشل على GitHub

أحيانًا خدمة الصوت المجانية (edge-tts) بتحجب سيرفرات الشركات. الحل: شغّل المشروع على جهازك:

```
pip install -r requirements.txt
# وكمان ثبّت ffmpeg
export PEXELS_API_KEY=مفتاحك
python generate.py --mode short
```

## ملاحظات مهمة

- الفيديوهات مجمّعة من مقاطع Pexels (مسموح استخدامها تجاريًا، راجع الشروط).
- يوتيوب بيقلل من المحتوى المكرر/الآلي بالكامل، فخلي السكريبت مميز وأضف لمستك.
- حجم الخط والتموضع للترجمة تقدر تعدله في `generate.py` (متغيرات `size` و`margin`).
