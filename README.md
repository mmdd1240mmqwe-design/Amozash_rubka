# SHADOW CASE 🕵️

ربات تلگرامی معمایی/کارآگاهی. هر بازی یه پرونده‌ی کاملاً تصادفی می‌سازه:
قربانی، ۴ مظنون با شخصیت متفاوت، ۴ مکان (یکی قفله)، سلاح، انگیزه و قاتل — همه رندوم.

مکانیک‌های واقعی (نه فقط متن):
- جستجوی مکان‌ها و پیدا کردن آیتم
- باز کردن قفل با مینی‌گیم حدس کد (Mastermind)
- بازجویی از مظنونین با اعتماد/سوءظن که تغییر می‌کنه
- نشون دادن مدرک به مظنون و دیدن واکنش واقعی
- ترکیب سرنخ‌ها برای نتیجه‌ی قطعی
- ماموریت فرعی تعمیر رادیو با مینی‌گیم چیدن قطعات به ترتیب درست
- گرسنگی/تشنگی/استقامت/سلامتی/اعتبار که واقعاً روی بازی اثر می‌ذاره
- ددلاین روزانه، اگه دیر کنی پرونده سرد می‌شه
- نتیجه‌گیری نهایی با چند پایان متفاوت

## فایل‌ها
- `bot.py` — نقطه‌ی شروع
- `config.py` — تنظیمات و مقادیر بازی
- `gamedata.py` — استخرهای داده و ساخت پرونده‌ی تصادفی
- `db.py` — دیتابیس SQLite
- `minigames.py` — منطق مینی‌گیم‌ها
- `keyboards.py` — دکمه‌های شیشه‌ای
- `handlers.py` — کل منطق بازی
- `requirements.txt`, `Procfile`, `railway.json`, `.env.example`

## نصب و اجرا (لوکال)
```bash
pip install -r requirements.txt
export BOT_TOKEN=توکن_رباتت
python bot.py
```

## گیت‌هاب
```bash
git init
git add .
git commit -m "Shadow Case"
git branch -M main
git remote add origin https://github.com/USERNAME/shadowcase-bot.git
git push -u origin main
```

## دیپلوی روی Railway
۱. [railway.app](https://railway.app) → New Project → Deploy from GitHub repo → ریپو رو انتخاب کن
۲. تب Variables → `BOT_TOKEN` رو با توکن واقعی ست کن
۳. Railway خودش از `requirements.txt` و `railway.json` استفاده می‌کنه و اجرا می‌کنه

## دستورات
- `/start` — شروع / ادامه‌ی پرونده
- `/newcase` — رها کردن پرونده‌ی فعلی و شروع یه پرونده‌ی کاملاً جدید
- `/status` — وضعیت فعلی
