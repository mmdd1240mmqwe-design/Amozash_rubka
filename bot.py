from rubka import Robot
from rubka.context import Message
from datetime import datetime, date, timedelta
import random
import json
import re
import time
import traceback
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import asyncio


async def maybe_await(value):
    """اگه مقدار برگشتی یه کوروتین بود (نسخه‌ی async کتابخونه)، منتظرش می‌مونیم؛
    اگه نه (نسخه‌ی sync)، همون مقدار رو مستقیم برمی‌گردونیم. این کار باعث میشه
    کد چه با نسخه‌ی sync و چه async کتابخونه‌ی rubka کار کنه."""
    if asyncio.iscoroutine(value):
        return await value
    return value


try:
    import requests
except Exception:
    requests = None

# =========================================================================
# توکنو اینجا بذار
# =========================================================================
bot = Robot(token="BICHDE0XWGLIJWDPFFHOJOMLUVNHILIOMBSNNEKPJGNKYTWNBYDGXIMQQCVENVYI")

# آیدی خودت (uid واقعی، نه یوزرنیم!) رو اینجا بذار.
ADMIN_ID = "u0HxhJk0ee6d86f064b9a17c3af3ed33"

# ⚠️ ادمین ویژه دوم: سینا
# نکته مهم: مقداری که برام فرستادی (@TOJiFOSHiGOR0) یه یوزرنیمه، نه UID!
# برای این‌که واقعا کار کنه، باید سینا خودش تو ربات بنویسه «آیدی من»
# و UID واقعی‌ای که ربات جواب میده رو همینجا جایگزین همین مقدار زیر کنی.
SINA_ADMIN_ID = "@TOJiFOSHiGOR0"  # <-- این رو با UID واقعی سینا عوض کن

# لیست همه‌ی ادمین‌های ویژه ربات (دسترسی کامل، مثل ارسال همگانی و عبور از قفل‌ها)
ADMIN_IDS = [ADMIN_ID, SINA_ADMIN_ID]


def is_bot_admin(uid):
    return str(uid) in [str(a) for a in ADMIN_IDS]


# یوزرنیم مالک ربات
OWNER_USERNAME = "@Kaveroxkop7"
OWNER_LINK = f"https://rubika.ir/{OWNER_USERNAME.lstrip('@')}"

# فایلی که کل اطلاعات کاربرا و گروه‌ها توش ذخیره میشه (تا با ری‌استارت ربات چیزی پاک نشه)
DATA_FILE = "persia_bot_data.json"

# =========================================================================
# نکته مهم: دکمه‌های شیشه‌ای (اینلاین) در نسخه فعلی کتابخونه rubka که تست شد
# کال‌بکشون به دست کد نمی‌رسید (هیچ‌وقت callback_handler صدا زده نمی‌شد).
# به همین خاطر کل ربات رو کاملا متنی (بدون دکمه) بازنویسی کردم تا ۱۰۰٪ کار کنه؛
# همه‌ی بازی‌ها (پنالتی، فرار از زندان، جرعت حقیقت، دروغ‌سنج) با فرستادن عدد/متن انجام میشن.
# =========================================================================


def get_uid(message):
    uid = getattr(message, "sender_id", None)
    if uid:
        return uid
    return message.chat_id


message_senders = {}
bot_message_ids = set()
processed_message_ids = set()  # جلوگیری از پردازش تکراری یه پیام (چند نمونه هم‌زمان یا fetch دوباره)
MAX_PROCESSED_IDS = 5000


async def bot_reply(message, text, **kwargs):
    try:
        result = await maybe_await(message.reply(text, **kwargs))
        if isinstance(result, dict):
            mid = result.get("data", {}).get("message_id")
            if mid:
                bot_message_ids.add(mid)
        return result
    except Exception:
        print("=" * 40)
        print("❌ خطا در message.reply - جزئیات کامل:")
        traceback.print_exc()
        print("=" * 40)
        try:
            result = await maybe_await(bot.send_message(message.chat_id, text, **kwargs))
            if isinstance(result, dict):
                mid = result.get("data", {}).get("message_id")
                if mid:
                    bot_message_ids.add(mid)
            return result
        except Exception:
            print("❌ خطا در send_message هم:")
            traceback.print_exc()
            return None


async def try_remove_user(chat_id, uid):
    """حذف واقعی عضو از گروه - چون این متد در rubka مستند نیست، چندتا حدس رو امتحان می‌کنه."""
    for method_name in ("kick_chat_member", "ban_chat_member", "kick_member", "remove_member", "ban_member"):
        if hasattr(bot, method_name):
            try:
                await maybe_await(getattr(bot, method_name)(chat_id, uid))
                return True
            except Exception as e:
                print("خطا در حذف عضو:", e)
    return False


async def try_delete_message(chat_id, message_id):
    """حذف یه پیام مشخص (مثلا پیام حاوی لینک) - چون متد رسمی مستند نیست، چندتا حدس رو امتحان می‌کنه."""
    if not message_id:
        return False
    for method_name in ("delete_message", "delete_messages", "remove_message"):
        if hasattr(bot, method_name):
            try:
                if method_name == "delete_messages":
                    await maybe_await(getattr(bot, method_name)(chat_id, [message_id]))
                else:
                    await maybe_await(getattr(bot, method_name)(chat_id, message_id))
                return True
            except Exception as e:
                print("خطا در حذف پیام:", e)
    return False


def is_forwarded_message(message):
    """تشخیص فوروارد بودن پیام - best effort، چون فیلد دقیقش تو مستندات rubka مشخص نیست."""
    try:
        for attr in ("is_forward", "forwarded", "forward_from"):
            if getattr(message, attr, None):
                return True
        raw = getattr(message, "raw_data", None)
        if isinstance(raw, dict):
            nm = raw.get("new_message", raw)
            if isinstance(nm, dict) and (nm.get("forwarded_from") or nm.get("is_forward")):
                return True
    except Exception:
        pass
    return False


users = {}
active_tictactoe = {}
active_guess = {}
active_penalty = {}   # {uid: {"shots": int, "goals": int}}
active_prison = {}    # {uid: {"node": node_id, "map": {"1": next_node, ...}}}
active_truth_dare = {}   # {uid: True}
active_lie_detector = set()  # {uid, uid, ...}
lottery = {"open": False, "participants": []}
locks = {}              # {chat_id: {"link": True, "spam": True, ...}}
spam_tracker = {}
chat_history = {}
warn_counts = {}        # {"chat_id|uid": تعداد اخطار}
registered_groups = {}  # {chat_id: {"owner": uid}}

LOCK_LABELS = {
    "link": "لینک",
    "spam": "اسپم",
    "badword": "الفاظ نامناسب",
    "mention": "منشن زیاد",
    "forward": "فوروارد",
}
LOCK_ICONS = {
    "link": "🔗", "spam": "🚫", "badword": "🤬", "mention": "📢", "forward": "↪️",
}

# اینجا هر کلمه‌ای که فکر می‌کنی نامناسبه رو اضافه کن، مثال:
# BADWORDS = ["کلمه۱", "کلمه۲"]
BADWORDS = ["کص", "کیر"]

RIDDLES = [
    ("چه چیزی هرچی از آن برداری بزرگ‌تر می‌شود؟", "چاله"),
    ("چیزی که دندان دارد ولی گاز نمی‌گیرد چیست؟", "شانه"),
    ("چه چیزی همیشه میاد ولی هیچوقت نمیرسه؟", "فردا"),
]

QUIZ = [
    ("پایتخت ایران کجاست؟", "تهران"),
    ("آب از چند اتم تشکیل شده؟", "3"),
    ("بزرگترین سیاره منظومه شمسی کدام است؟", "مشتری"),
]

# ---------------------------------------------------------------------------
# جرعت حقیقت 🎭
# ---------------------------------------------------------------------------
TRUTHS = [
    "آخرین دروغی که به یکی از اعضای این گروه گفتی چی بود؟",
    "تا حالا شده از یکی تو همین گروه خوشت بیاد؟",
    "بدترین نمره‌ای که تا حالا گرفتی چند بوده؟",
    "خجالت‌آورترین اتفاقی که برات افتاده رو بگو",
    "اگه یه ابرقدرت داشتی که هیچکس نفهمه، چیکارش می‌کردی؟",
    "آخرین باری که گریه کردی کی بود و چرا؟",
    "یه رازتو که مشکلی نداره بگی، بگو",
    "بدترین هدیه‌ای که گرفتی چی بوده؟",
    "تا حالا به کسی گفتی دوستش داری ولی راست نبوده؟",
    "از خودت چی رو دوست نداری؟",
    "بامزه‌ترین لقبی که بهت دادن چی بوده؟",
    "تا حالا زیر امتحان تقلب کردی؟",
    "بدترین کار احمقانه‌ای که کردی چی بوده؟",
    "اگه می‌تونستی یه چیزو تو گذشته عوض کنی چی بود؟",
    "از کدوم عضو این گروه بیشتر خوشت میاد؟ (به شوخی هم میشه گفت 😄)",
    "بزرگترین ترست چیه؟",
    "آخرین باری که به کسی حسادت کردی کی بود؟",
    "یه دروغ شاخ که تا حالا گفتی رو بگو",
    "بدترین خاطره مدرسه‌ت چیه؟",
    "اگه یه شب فقط با یه نفر می‌تونستی حرف بزنی، کی بود؟",
]

DARES = [
    "یه عکس از خودت با یه حالت خنده‌دار بفرست",
    "۵ ثانیه فقط با شکلک به همه سلام کن",
    "یه آهنگ زشت با صدای بلند برامون بخون (تایپ کن چی می‌خوندی)",
    "به یکی از اعضای گروه بگو چقدر باحاله",
    "پیامتو فقط با ایموجی بفرست، بدون هیچ حرفی",
    "یه جوک بگو که همه بخندن",
    "یه رقص خنده‌دار توصیف کن که الان انجامش دادی",
    "۱۰ ثانیه فقط بگو «موز موز موز...»",
    "اسم حیوان مورد علاقتو با صدای اون حیوان تعریف کن",
    "به یکی از دوستات پیام بده و بگو «امروز خیلی بامزه‌ای» و نتیجه‌شو بگو",
    "یه شعر مسخره فی‌البداهه بساز",
    "بگو الان دقیقا چه لباسی پوشیدی",
    "با لهجه غلیظ یه جمله تایپ کن",
    "اسم خودتو برعکس بنویس",
    "یه خاطره خجالت‌آور تعریف کن",
    "۳۰ ثانیه فقط شکلک خنده بفرست 😂😂😂",
    "بگو الان چند تا اپلیکیشن باز داری",
    "یه استوری مسخره در مورد خودت بساز و تعریف کن",
    "صداتو ضبط کن و بگو «من پادشاه این گروهم» (یا فقط تصورشو بگو 😄)",
    "به بامزه‌ترین شکل ممکن خداحافظی کن",
]

LIE_DETECTOR_QUESTIONS = [
    "امروز صبح دندوناتو مسواک زدی؟",
    "تا حالا به کسی دروغ گفتی که خوشگلی؟",
    "غذای دیشب رو کامل دوست داشتی؟",
    "تو دلت به یکی تو همین گروه کراش داری؟ 😏",
    "تا حالا زیر امتحان تقلب کردی؟",
    "فکر می‌کنی از من باهوش‌تری؟ 🤖",
    "امروز به کسی دروغ گفتی؟",
    "فکر می‌کنی الان زیادی خوش‌تیپی؟ 😎",
    "تا حالا وانمود کردی خوابیدی که کسی مزاحمت نشه؟",
    "فکر می‌کنی برنده این بازی میشی؟",
]

# ---------------------------------------------------------------------------
# فروشگاه اصلی - آیتم‌های بیشتر و قیمت‌های بالاتر تا خریدشون واقعا ارزش داشته باشه
# ---------------------------------------------------------------------------
SHOP_ITEMS = {
    "کلاه ساده": 300,
    "عینک آفتابی": 450,
    "شمشیر جنگی": 900,
    "سپر آهنین": 1200,
    "چکمه سفری": 1600,
    "تاج طلایی": 2500,
    "جبه شاهانه": 3200,
    "حلقه جادویی": 4200,
    "عصای اژدها": 5500,
    "تاج الماس": 8000,
    "زره افسانه‌ای": 12000,
    "گنج پادشاهی": 20000,
}

CREATURES = ["اژدها 🐉", "ققنوس 🔥", "یونیکورن 🦄", "گرگ 🐺", "عقاب 🦅", "ببر 🐯", "کریکن 🐙", "ققنوس یخی ❄️🔥"]

# ---------------------------------------------------------------------------
# فروشگاه مخصوص بازی پنالتی - آیتم بیشتر و گرون‌تر
# ---------------------------------------------------------------------------
PENALTY_SHOP = {
    "توپ طلایی": 800,
    "توپ آتشین": 700,
    "کفش ویژه": 1000,
    "ستاره شانس": 900,
    "کفش سرعتی": 1500,
    "توپ الماسی": 2500,
    "مدال قهرمانی": 4000,
}
PENALTY_EMOJI = {
    "توپ طلایی": "🥇",
    "توپ آتشین": "🔥",
    "کفش ویژه": "👟",
    "ستاره شانس": "⭐",
    "کفش سرعتی": "💨",
    "توپ الماسی": "💎",
    "مدال قهرمانی": "🏆",
}
# آیتم‌هایی که فقط سکه‌ی هر گل رو زیاد می‌کنن
PENALTY_COIN_BONUS = {
    "توپ طلایی": 5,
    "کفش سرعتی": 8,
    "توپ الماسی": 15,
    "مدال قهرمانی": 25,
}

PENALTY_ZONES = [
    ("pen_tl", "↖️ بالا چپ"),
    ("pen_tc", "⬆️ بالا وسط"),
    ("pen_tr", "↗️ بالا راست"),
    ("pen_bl", "↙️ پایین چپ"),
    ("pen_bc", "⬇️ پایین وسط"),
    ("pen_br", "↘️ پایین راست"),
]

# ---------------------------------------------------------------------------
# داستان بازی «فرار از زندان»
# ---------------------------------------------------------------------------
PRISON_NODES = {
    "start": {
        "text": "🌙 نیمه‌شبِ زندونه... نگهبان‌ها خسته و خواب‌آلودن، این بهترین فرصته.\nصدای قدم از دور میاد. کدوم مسیر رو انتخاب می‌کنی؟",
        "options": [("p_tunnel", "🕳 تونل زیرزمینی"), ("p_wall", "🧱 دیوار حیاط"), ("p_gate", "🚪 درِ اصلی با لباس نگهبان")],
    },
    "p_tunnel": {
        "text": "وارد یه تونل تاریک و نمور شدی... صدای آب از یه طرف میاد. دو راه جلوته:",
        "options": [("p_tunnel_left", "⬅️ مسیر چپ (صدای قدم)"), ("p_tunnel_right", "➡️ مسیر راست (صدای آب)")],
    },
    "p_tunnel_left": {
        "outcome": "lose",
        "text": "❌ یهو یه نگهبان با چراغ‌قوه جلوت سبز شد: «کجا فکر کردی داری میری؟!»\nدستگیر شدی و برگردوندنت به سلول.",
    },
    "p_tunnel_right": {
        "text": "به یه لوله فاضلاب رسیدی که به بیرون از دیوار وصله. یه دریچه‌ی زنگ‌زده بالای سرته.",
        "options": [("p_tunnel_open", "🔓 دریچه رو باز کن و برو بیرون"), ("p_tunnel_back", "↩️ برگرد، ممکنه پیدات کنن")],
    },
    "p_tunnel_open": {
        "outcome": "win",
        "text": "🎉 دریچه باز شد! از فاضلاب زدی بیرون، زیر نور ماه... آزادی! فرار موفقیت‌آمیز بود.",
    },
    "p_tunnel_back": {
        "outcome": "lose",
        "text": "😓 برگشتی و درست وسط راهرو با نگهبان‌ها چشم‌تو‌چشم شدی. گرفتار شدی.",
    },
    "p_wall": {
        "text": "از یه لوله بالا رفتی و به دیوار حیاط رسیدی. نور نگهبانی داره می‌چرخه سمتت.",
        "options": [("p_wall_hide", "🙈 قایم شو پشت سطل زباله"), ("p_wall_jump", "🤸 سریع بپر اون‌ور دیوار")],
    },
    "p_wall_hide": {
        "chance": 0.7,
        "win_text": "😮‍💨 نور از کنارت رد شد و ندیدت! از فرصت استفاده کردی و پریدی اون‌ور دیوار. آزاد شدی! 🎉",
        "lose_text": "👮 نگهبان صدای نفس‌هاتو شنید و دستگیرت کرد.",
    },
    "p_wall_jump": {
        "chance": 0.5,
        "win_text": "🤕 با یه ضربه سخت پریدی پایین ولی موفق شدی فرار کنی! آزادی! 🎉",
        "lose_text": "💥 موقع پریدن صدای بدی داد، نگهبان‌ها ریختن سرت.",
    },
    "p_gate": {
        "text": "با لباس دزدیده‌شده نگهبان جلو درِ اصلی وایسادی. یه نگهبان صدات می‌زنه: «هی! کجا می‌ری؟»",
        "options": [("p_gate_calm", "😎 خونسرد بمون: «می‌رم پست نگهبانی»"), ("p_gate_run", "🏃 فرار کن")],
    },
    "p_gate_calm": {
        "chance": 0.65,
        "win_text": "👌 باورش شد و ردت کرد. از درِ اصلی زدی بیرون. آزادی! 🎉",
        "lose_text": "🤨 یه چیزی تو صدات شک‌برانگیز بود، فهمید و دستگیرت کرد.",
    },
    "p_gate_run": {
        "chance": 0.35,
        "win_text": "💨 با سرعت از کنارش رد شدی و گم‌وگور شدی تو شهر. آزادی! 🎉",
        "lose_text": "🚨 آژیر خطر به صدا در اومد و گرفتنت.",
    },
}

JOKES = [
    "😂 معلم گفت چرا تکلیف ننوشتی؟ گفتم می‌خواستم شما هم استراحت کنید!",
    "🤣 یارو رفت دکتر، گفت حافظه‌م ضعیفه. دکتر گفت از کی؟ گفت چی از کی؟",
    "😆 یارو انقدر خوابش میومد، تو خواب هم خوابش برد!",
    "😂 یارو زنگ زد آتش‌نشانی گفت خونمون آتیش گرفته! گفتن چیکار کنیم؟ گفت هیچی، فقط بیاید ببینید چه صحنه باحالیه!",
    "🤣 یه بار یه بابایی رفت آرایشگاه گفت موهامو مثل پدرم بزن، آرایشگر گفت پس اول باید کچل کنمت!",
    "😅 یارو رفت مصاحبه کاری، گفتن نقطه‌ضعفت چیه؟ گفت صداقتم زیاده. گفتن این که ضعف نیست. گفت مهم نیست، من که گفتم صداقتم زیاده!",
    "😆 دو تا دوست باهم حرف می‌زدن، یکی گفت دیشب خواب دیدم دارم ۱۰۰۰۰۰ تومن پیدا می‌کنم. اون یکی گفت خب چیشد؟ گفت بیدار شدم رفت تو حلقم!",
    "🤣 بچه به باباش گفت بابا چرا انقدر دیر اومدی؟ باباش گفت ترافیک بود عزیزم. بچه گفت ولی تو که با دوچرخه میری!",
    "😂 یارو رفت دکتر گفت دکتر من هرچی میگم فراموش می‌کنم. دکتر گفت از کی این مشکلو داری؟ گفت کدوم مشکل؟",
    "😆 معلم پرسید: عدد پی چیه؟ دانش‌آموز گفت: یه خوراکی خوشمزه‌ست!",
    "😂 یارو تو مصاحبه گفتن رزومه‌ت کجاست؟ گفت تو گوگل سرچ کن اسممو، پیدا میشه!",
    "🤣 یه نفر زنگ زد پلیس گفت ماشینمو دزدیدن ولی رادیوشو روشن گذاشتم که خسته نشه!",
    "😆 پسر به باباش گفت بابا چرا موهات سفید شده؟ باباش گفت هر بار که تو کار بدی می‌کنی یه تار موم سفید میشه. پسر گفت پس بابابزرگ چرا سرش کامل سفیده؟",
    "😂 یارو رفت فروشگاه گفت یه کیلو صبر می‌خوام. فروشنده گفت صبر که وزن نداره. گفت پس یه کیلو حوصله بده!",
    "🤣 معلم گفت جمله بساز با کلمه‌ی «گاهی». دانش‌آموز نوشت: گاهی اوقات درس نمی‌خونم!",
    "😂 یارو رفت آرایشگاه گفت موهامو کوتاه کن ولی نه خیلی، آرایشگر گفت پس یکم بلندتر بذارم؟ گفت نه همون کوتاه!",
    "🤣 یارو زنگ زد به دوستش گفت کجایی؟ گفت تو ترافیکم. گفت خب ماشینتو چیکار کردی؟",
    "😆 معلم پرسید کی درسشو نخونده؟ همه دست بلند کردن جز یه نفر. معلم گفت آفرین تو، گفت من دیشب نبودم!",
    "😂 یارو رفت دکتر گفت دکتر من وقتی میخندم صدام عجیب میشه. دکتر گفت بذار ببینم، یارو خندید دکتر هم خندید گفت واقعا عجیبه!",
    "🤣 بابابزرگه به نوه‌ش گفت من تو دوران خودم پیاده تا مدرسه می‌رفتم. نوه‌ش گفت خب الان چرا با ماشین میری بازنشستگی می‌گیری؟",
    "😆 یارو رفت نانوایی گفت یه نون بده. نانوا گفت داغه‌ها! گفت مهم نیست تا برسم خونه سرد میشه!",
    "😂 معلم گفت جمع ۲ و ۲ چند میشه؟ دانش‌آموز گفت بستگی داره چقدر عجله داری!",
    "🤣 یارو رفت باشگاه گفت می‌خوام لاغر شم. مربی گفت اول بگو چقدر می‌خوری. یارو گفت خب دیگه بستگی داره چقدر باشه!",
    "😆 دو تا دوست تو اتوبوس، یکی گفت چقدر گرمه اینجا! اون یکی گفت پنجره رو باز کن. گفت نمیشه، اتوبوسیم نه خونه!",
    "😂 یارو گفت من عاشق ورزشم، فقط از دور نگاش می‌کنم دیگه بسمه!",
];

CHALLENGES = [
    "پول یا عشق؟ 💰❤️", "تابستون یا زمستون؟ ☀️❄️", "دریا یا کوه؟ 🌊⛰️", "چای یا قهوه؟ ☕",
    "شب یا صبح؟ 🌙☀️", "گربه یا سگ؟ 🐱🐶", "پیتزا یا برگر؟ 🍕🍔", "کتاب یا فیلم؟ 📚🎬",
    "شهر یا روستا؟ 🏙️🏡", "بارون یا آفتاب؟ 🌧️☀️", "از اتاقت یه عکس بده ببینیم چه شکلیه 📸",
    "شماره‌تو بده ببینیم راست میگی رفیقی 😄", "یه خاطره خنده‌دار از خودت تعریف کن",
    "بگو امروز چند تا لیوان آب خوردی", "یه شعر یا ترانه بخون برامون", "رنگ مورد علاقت چیه؟",
    "غذای مورد علاقتو بگو", "یه جوک تعریف کن که همه بخندن", "موزیک مورد علاقتو بگو",
    "۵ ثانیه چشماتو ببند، بعد بگو چی تو ذهنت اومد", "یه چیز جالب درباره خودت بگو که کسی نمی‌دونه",
    "بگو امروز صبحونه چی خوردی", "پیامتو فقط با شکلک بفرست، بدون هیچ حرفی", "بگو الان تو کدوم شهری",
    "یه آهنگ به بقیه پیشنهاد بده", "امتحان یا تعطیلی؟ 📝🎉", "پول نقد یا کارت هدیه؟ 💵🎁",
    "تنهایی یا شلوغی؟ 🧘👥", "خنده یا گریه تو فیلما؟ 😂😢", "پیاده‌روی یا دوچرخه‌سواری؟ 🚶🚴",
    "صبح زود بیدار شدن یا شب بیدار موندن؟ 🌅🌃", "بازی فکری یا بازی اکشن؟ 🧩🎮",
    "سفر تنها یا سفر گروهی؟ ✈️👨‍👩‍👧‍👦", "خرید حضوری یا خرید اینترنتی؟ 🛍️💻",
    "بگو الان چند نفر آنلاینن تو گروه", "اگه یه ابرقدرت داشتی چی می‌خواستی؟",
    "یه رازتو (که مشکلی نداره بگی) با ما درمیون بذار", "بگو دیشب چه ساعتی خوابیدی",
    "اگه یه روز پول‌دار بشی اول چیکار می‌کنی؟", "موبایل یا لپ‌تاپ؟ 📱💻",
    "اگه یه روز رئیس این گروه بودی چیکار می‌کردی؟ 👑", "بامزه‌ترین خاطره‌ی مدرسه‌تو بگو 🏫",
    "اگه می‌تونستی یه ابرقهرمان باشی کدوم می‌شدی؟ 🦸", "یه دروغ شاخ بگو که همه بخندن 😂",
    "قهوه تلخ یا شیرین؟ ☕", "فیلم ترسناک یا کمدی؟ 👻😂", "کنسرت یا سینما؟ 🎤🎬",
    "پیاده رفتن یا تاکسی گرفتن؟ 🚶🚕", "صبحونه سنگین یا سبک؟ 🍳🥐",
    "تعطیلات تابستون یا زمستون؟ ☀️❄️", "دوش صبح یا شب؟ 🚿", "چیپس یا پفک؟ 🍟🍿",
    "شکلات تلخ یا شیری؟ 🍫", "بستنی وانیلی یا شکلاتی؟ 🍦", "پیتزا پپرونی یا مخصوص؟ 🍕",
    "بارون بازی کردی تا حالا؟ ☔ اگه آره بگو کی بود", "بلندترین خوابی که رفتی چند ساعت بود؟",
    "اگه یه حیوون خونگی داشتی چی می‌خواستی باشه؟ 🐾",
    "دوست داری تو کدوم کشور زندگی کنی؟ 🌍",
    "اگه یه روز نامرئی می‌شدی چیکار می‌کردی؟ 👻",
    "بامزه‌ترین پیامی که تا حالا گرفتی رو تعریف کن",
    "اگه می‌تونستی زمان سفر کنی، به گذشته می‌رفتی یا آینده؟ ⏳",
    "دوست داری کدوم شخصیت کارتونی باشی؟ 🎨",
    "بهترین هدیه‌ای که دادی چی بود؟ 🎁",
    "اگه یه روز فقط اجازه داشتی یه جمله بگی چی می‌گفتی؟",
    "بامزه‌ترین اسمی که شنیدی چی بود؟",
    "اگه می‌تونستی یه ابرقدرت بدی به یکی از اعضای گروه، به کی می‌دادی و چی؟",
    "دوست داری آهنگ‌سازی کنی یا خواننده بشی؟ 🎵",
    "اولین چیزی که صبح چک می‌کنی چیه؟ 📱",
    "بامزه‌ترین شکلک مورد علاقتو بفرست",
    "اگه یه روز رئیس‌جمهور بودی اولین کارت چی بود؟",
    "دوست داری تو یه جزیره تنها باشی یا شهر شلوغ؟ 🏝️🏙️",
    "بامزه‌ترین حیوونی که دیدی چی بود؟",
    "چند بار امروز خندیدی؟ 😄",
    "اگه یه شغل عجیب می‌تونستی داشته باشی چی بود؟",
    "بگو الان چند تا پیام نخونده داری",
    "دوست داری وقتتو بیشتر با کتاب بگذرونی یا فیلم؟ 📖🎬",
    "بامزه‌ترین دوست‌تو معرفی کن (بدون اسم واقعی اگه دوست نداری)",
    "اگه یه روز می‌تونستی پرواز کنی، کجا می‌رفتی؟ 🕊️",
    "دوست داری بیشتر سفر کنی یا خونه بمونی؟ ✈️🏠",
    "بامزه‌ترین چیزی که امروز دیدی چی بود؟",
    "اگه یه سکه جادویی پیدا می‌کردی چه آرزویی می‌کردی؟ 🪙",
    "دوست داری موسیقی پاپ گوش بدی یا سنتی؟ 🎶",
    "بگو الان چند تا تب مرورگر باز داری",
    "اگه یه روز می‌تونستی با یه شخصیت تاریخی حرف بزنی، با کی؟",
    "بامزه‌ترین خواب دیشبتو تعریف کن",
    "دوست داری بازیگر بشی یا کارگردان؟ 🎬",
    "اگه یه روز میلیاردر می‌شدی اول چی می‌خریدی؟ 💵",
    "بگو الان چند نفر تو گروه رو واقعا می‌شناسی",
    "دوست داری کوهنوردی کنی یا شنا؟ ⛰️🏊",
    "بامزه‌ترین لهجه‌ای که دوست داری تقلید کنی چیه؟",
    "اگه یه روز می‌تونستی حیوونا حرف بزنن، از کدوم حیوون اول می‌پرسیدی؟",
    "بگو دوست داری کدوم بازی ویدیویی رو انجام بدی 🎮",
    "بامزه‌ترین اتفاقی که تو خیابون دیدی چی بود؟",
    "دوست داری معلم بشی یا دانش‌آموز بمونی؟ 📚",
    "اگه یه روز می‌تونستی نامرئی بشی، اول کجا می‌رفتی؟",
    "بامزه‌ترین آهنگی که این هفته گوش دادی چی بود؟",
]

EMOJIS_LIST = ["🦊", "🐼", "🦁", "🐯", "🐺", "🐸", "🐵", "🦉", "🐧", "🦄",
               "🐲", "🐙", "🦋", "🐝", "🦔", "🐨", "🐰", "🦝", "🦅", "🐬"]

PERSIAN_MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
                  "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]

GREETINGS = [
    "سلام داداش گلم ❤️ چه خوب اومدی! امیدوارم امروز حسابی بهت خوش بگذره 🌸",
    "سلاممم 😄 دلم برات تنگ شده بود! کجا بودی این‌همه وقت؟",
    "درود بر تو رفیق عزیز 🌹 خوش اومدی به جمعمون، جات خیلی خالی بود",
    "سلام رفیق ✌️ امروز روز خوبیه واسه گپ زدن و کلی بازی کردن 🎮",
    "سلام قهرمان! 🦸 آماده‌ای امروزو بترکونیم؟",
    "به‌به سلام! 😎 حالا شد، تازه گروه گرم شد که تو اومدی",
    "سلام سلام 👋 چه خبرا رفیق باحال من؟",
    "اوه سلام! 🌟 دقیقا منتظر یه پیام باحال مثل مال تو بودم",
    "سلام عزیز دلم ❤️ امیدوارم حالت عالی باشه",
    "سلاااام 🙌 بگو ببینم امروز چه کارایی می‌خوایم بکنیم؟",
]
HOW_ARE_YOU = [
    "مرسی، خوبم 😄 تو چطوری؟ امیدوارم روزت پر انرژی و شاد باشه!",
    "عالی‌ام 😎 هر لحظه که باهات چت می‌کنم بهتر میشم! تو چطوری داداش؟",
    "خوبم داداش ❤️ تو بگو از خودت، چه خبرا؟ اتفاق باحالی افتاده؟",
    "همیشه سرحالم چون اینجا کلی رفیق باحال دارم 🙌 خودت چطوری؟",
    "بد نیستم، فقط منتظر یه بازی خوب بودم 😄 تو حالت چطوره؟",
    "خوبم مرسی که پرسیدی 🌸 تو چی، امروز بهت خوش گذشت؟",
    "عالیم، انرژیمو از پیام‌های شما می‌گیرم 🔋😄 تو چطوری؟",
    "خیلی خوبم، امروز کلی باهات حرف زدیم و کیف کردم 😄 تو چی؟",
]
THANKS_REPLIES = [
    "❤️ خواهش می‌کنم، همیشه در خدمتتم.",
    "🙏 وظیفمه داداش، هر وقت خواستی صدام کن.",
    "😊 قربونت، خوشحال میشم کمکت کرده باشم.",
    "🌸 خواهش می‌کنم عزیز، همیشه اینجام برات.",
    "😄 نوش جونت، هر کاری بگی برات انجام میدم.",
    "🙌 کاری نکردم که، خودتی رفیق!",
]
GOODBYE_REPLIES = [
    "👋 فعلاً داداش، زود برگرد!",
    "🌙 خدانگهدار، منتظرتم برای گپ بعدی 😄",
    "✌️ به امید دیدار، مراقب خودت باش!",
    "😄 بای بای رفیق، دلم برات تنگ میشه!",
    "🌟 خدافظ عزیز، حواست به خودت باشه",
    "👋 فعلا! زود بیا که بدون تو حوصله‌مون سر میره",
]

INTRO_REPLIES = ["اسمم پرسیاست 😄 دستیار همیشگی این گروه!", "من پرسیام، خودتو معرفی کن ببینم کی هستی 😊"]

# ---------------------------------------------------------------------------
# تبدیل تاریخ میلادی به شمسی
# ---------------------------------------------------------------------------
def gregorian_to_jalali(gy, gm, gd):
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    if gy > 1600:
        jy = 979
        gy -= 1600
    else:
        jy = 0
        gy -= 621
    gy2 = gy + 1 if gm > 2 else gy
    days = (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100) + ((gy2 + 399) // 400) - 80 + gd + g_d_m[gm - 1]
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + (days % 31)
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + ((days - 186) % 30)
    return jy, jm, jd


def get_jalali_date_str():
    now = datetime.now()
    jy, jm, jd = gregorian_to_jalali(now.year, now.month, now.day)
    return f"{jd} {PERSIAN_MONTHS[jm-1]} {jy}"


def get_user_emoji(uid):
    s = str(uid)
    total = sum(ord(ch) for ch in s)
    return EMOJIS_LIST[total % len(EMOJIS_LIST)]


async def get_display_name(bot, message, uid):
    chat_id = getattr(message, "chat_id", None)
    try:
        name = await maybe_await(bot.get_name(uid))
        if name:
            return name
    except Exception:
        pass
    if chat_id and chat_id != uid:
        try:
            name = await maybe_await(bot.get_name(chat_id))
            if name:
                return name
        except Exception:
            pass
    try:
        chat_info = await maybe_await(bot.get_chat(uid))
        if isinstance(chat_info, dict):
            data = chat_info.get("data", chat_info)
            chat_obj = data.get("chat", data) if isinstance(data, dict) else {}
            first = chat_obj.get("first_name")
            last = chat_obj.get("last_name")
            if first:
                return (str(first) + (" " + str(last) if last else "")).strip()
    except Exception:
        pass
    raw = getattr(message, "raw_data", None)
    if isinstance(raw, dict):
        sender = raw.get("sender") or raw.get("new_message", {}).get("sender") or {}
        first = sender.get("first_name") or raw.get("first_name")
        last = sender.get("last_name") or raw.get("last_name")
        if first:
            return (str(first) + (" " + str(last) if last else "")).strip()
    return None


async def resolve_display_name(bot, message, uid, u):
    """اسم نمایشی رو با این ترتیب تعیین می‌کنه: اسم دلخواهی که خود کاربر ست کرده، بعد تلاش برای گرفتن اسم واقعی، بعد پیام راهنما."""
    if u.get("nickname"):
        return u["nickname"]
    name = await get_display_name(bot, message, uid)
    if name:
        return name
    return "کاربر ناشناس (با «تنظیم اسم [نام]» اسمتو خودت انتخاب کن)"


def resolve_emoji(u, uid):
    if u.get("custom_emoji"):
        return u["custom_emoji"]
    return get_user_emoji(uid)


def update_message_counters(u):
    today = date.today()
    d_str = today.isoformat()
    iso = today.isocalendar()
    w_str = f"{iso[0]}-W{iso[1]}"
    m_str = today.strftime("%Y-%m")

    if u["msg_daily"]["date"] != d_str:
        u["msg_daily"] = {"date": d_str, "count": 0}
    u["msg_daily"]["count"] += 1

    if u["msg_weekly"]["week"] != w_str:
        u["msg_weekly"] = {"week": w_str, "count": 0}
    u["msg_weekly"]["count"] += 1

    if u["msg_monthly"]["month"] != m_str:
        u["msg_monthly"] = {"month": m_str, "count": 0}
    u["msg_monthly"]["count"] += 1


def get_daily_luck(u):
    today = date.today().isoformat()
    first_time = False
    if u.get("luck_date") != today:
        u["luck_date"] = today
        u["luck_value"] = random.randint(1, 100)
        first_time = True
    return u["luck_value"], first_time


def get_user(uid):
    if uid not in users:
        users[uid] = {
            "xp": 0, "coins": 100, "wins": 0, "games": 0,
            "messages": 0, "last_daily": None, "streak": 0,
            "items": [], "creatures": [],
            "title": None, "origin": None, "nickname": None, "custom_emoji": None,
            "luck_date": None, "luck_value": None,
            "chat_id": None, "pv_chat_id": None,
            "penalty_items": [],
            "penalty": {"goals": 0, "misses": 0, "streak": 0, "best_streak": 0},
            "prison": {"wins": 0, "losses": 0},
            "msg_daily": {"date": None, "count": 0},
            "msg_weekly": {"week": None, "count": 0},
            "msg_monthly": {"month": None, "count": 0},
        }
    return users[uid]


def get_level(xp):
    return 1 + xp // 100


def add_xp(uid, amount):
    u = get_user(uid)
    u["xp"] += amount
    return u["xp"]


def add_coins(uid, amount):
    u = get_user(uid)
    u["coins"] += amount
    return u["coins"]


def get_badge(xp):
    if xp >= 500:
        return "🥇 استاد"
    elif xp >= 200:
        return "🥈 حرفه‌ای"
    return "🥉 تازه‌کار"


def progress_bar(current, total, length=10):
    total = max(total, 1)
    filled = int(length * min(current, total) / total)
    return "█" * filled + "░" * (length - filled)


def get_rank_position(uid):
    ranking = sorted(users.items(), key=lambda x: x[1]["xp"], reverse=True)
    for i, (u_id, _) in enumerate(ranking):
        if u_id == uid:
            return i + 1
    return "-"


def is_group(chat_id):
    return str(chat_id).startswith("g")


def get_locks(chat_id):
    if chat_id not in locks:
        locks[chat_id] = {k: True for k in LOCK_LABELS}
    else:
        for k in LOCK_LABELS:
            locks[chat_id].setdefault(k, True)
    return locks[chat_id]


def is_owner(chat_id, uid):
    return registered_groups.get(chat_id, {}).get("owner") == uid


async def handle_violation(message, chat_id, uid, reason):
    key = f"{chat_id}|{uid}"
    warn_counts[key] = warn_counts.get(key, 0) + 1
    if warn_counts[key] == 1:
        await bot_reply(message, f"⚠️ اخطار! به خاطر «{reason}» این بار اخطار می‌گیری، دفعه بعد از گروه حذفت می‌کنم.")
    else:
        removed = await try_remove_user(chat_id, uid)
        if removed:
            await bot_reply(message, f"🚫 به خاطر {reason} از گروه حذف شدی.")
        else:
            await bot_reply(message, f"🚫 باید به خاطر {reason} حذف می‌شدی، ولی کتابخونه rubka فعلا متد رسمی حذف عضو رو پشتیبانی نمی‌کنه.")
        warn_counts[key] = 0


# ---------------------------------------------------------------------------
# فونت کلفت (بولد) برای برندینگ - چون rubka فرمت‌بندی رسمی مستند نداره،
# از حروف یونیکد بولد استفاده می‌کنیم که تو هر پلتفرمی کلفت نمایش داده میشه.
# ---------------------------------------------------------------------------
def to_bold(text):
    result = []
    for ch in text:
        if 'A' <= ch <= 'Z':
            result.append(chr(0x1D400 + (ord(ch) - ord('A'))))
        elif 'a' <= ch <= 'z':
            result.append(chr(0x1D41A + (ord(ch) - ord('a'))))
        elif '0' <= ch <= '9':
            result.append(chr(0x1D7CE + (ord(ch) - ord('0'))))
        else:
            result.append(ch)
    return "".join(result)


BOT_BRAND = to_bold("VANTAPERSIA BOT")


# ---------------------------------------------------------------------------
# ماشین‌حساب متنی (جمع، تفریق، ضرب، تقسیم)
# ---------------------------------------------------------------------------
MATH_WORD_OPS = {
    "به علاوه": "+", "بعلاوه": "+", "جمع": "+",
    "منها": "-", "تفریق": "-",
    "ضربدر": "*", "ضرب در": "*", "ضرب": "*",
    "تقسیم بر": "/", "تقسیم": "/",
}


async def handle_math_query(message, text_raw):
    has_symbol = any(s in text_raw for s in ["+", "*", "×", "÷", "/"])
    has_word = any(w in text_raw for w in MATH_WORD_OPS)
    if not (has_symbol or has_word):
        return False

    t = text_raw.replace("×", "*").replace("÷", "/")
    for word, op in MATH_WORD_OPS.items():
        if word in t:
            t = t.replace(word, f" {op} ")
            break

    match = re.search(r'(-?\d+(?:\.\d+)?)\s*([+\-*/])\s*(-?\d+(?:\.\d+)?)', t)
    if not match:
        return False

    a = float(match.group(1))
    op = match.group(2)
    b = float(match.group(3))

    if op == "/" and b == 0:
        await bot_reply(message, "❌ تقسیم بر صفر امکان‌پذیر نیست!")
        return True

    if op == "+":
        result = a + b
    elif op == "-":
        result = a - b
    elif op == "*":
        result = a * b
    else:
        result = a / b

    if result == int(result):
        result = int(result)

    op_label = {"+": "جمع", "-": "تفریق", "*": "ضرب", "/": "تقسیم"}[op]
    a_disp = int(a) if a == int(a) else a
    b_disp = int(b) if b == int(b) else b
    await bot_reply(message, f"🧮 {op_label}:\n{a_disp} {op} {b_disp} = {result}")
    return True


# ---------------------------------------------------------------------------
# تبدیل ارز به تومان (دلار، یورو، یوان، درهم، پوند، لیر)
# نکته: این تابع از سایت tgju قیمت لحظه‌ای می‌گیره. اگه سایت در دسترس نبود
# یا ساختار جوابش عوض شد، پیام خطای مناسب برمی‌گردونه.
# ---------------------------------------------------------------------------
CURRENCY_KEYWORDS = {
    "دلار": "price_dollar_rl",
    "یورو": "price_eur",
    "یوان": "price_cny",
    "پوند": "price_gbp",
    "درهم": "price_aed",
    "لیر": "price_try",
}

CURRENCY_CACHE = {"data": None, "time": 0}
CURRENCY_TTL = 300  # ۵ دقیقه کش می‌کنیم تا سایت رو زیاد بمباران نکنیم


CURRENCY_HEADERS = {
    # بدون یه User-Agent شبیه مرورگر، خیلی سایت‌ها (از جمله tgju) درخواست رباتی رو رد می‌کنن یا جواب خالی میدن
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.tgju.org/",
}


def fetch_currency_rates():
    if requests is None:
        print("❌ کتابخونه requests نصب نیست. با دستور: pip install requests نصبش کن.")
        return None
    now = time.time()
    if CURRENCY_CACHE["data"] and now - CURRENCY_CACHE["time"] < CURRENCY_TTL:
        return CURRENCY_CACHE["data"]
    try:
        resp = requests.get("https://call5.tgju.org/ajax.json", headers=CURRENCY_HEADERS, timeout=8)
        print("📡 وضعیت درخواست قیمت ارز:", resp.status_code)
        if resp.status_code != 200:
            print("❌ سایت tgju جواب موفق نداد. متن پاسخ (۲۰۰ کاراکتر اول):", resp.text[:200])
            return CURRENCY_CACHE["data"]
        data = resp.json()
        current = data.get("current", {})
        if not current:
            print("❌ ساختار جواب سایت عوض شده. کلیدهای موجود در data:", list(data.keys()))
            return CURRENCY_CACHE["data"]
        rates = {}
        for fa_name, key in CURRENCY_KEYWORDS.items():
            item = current.get(key)
            if item:
                try:
                    price_rial = float(str(item.get("p", "0")).replace(",", ""))
                    if price_rial > 0:
                        rates[fa_name] = price_rial / 10  # ریال به تومان
                except Exception:
                    pass
            else:
                print(f"⚠️ کلید «{key}» برای «{fa_name}» تو جواب سایت پیدا نشد.")
        if rates:
            CURRENCY_CACHE["data"] = rates
            CURRENCY_CACHE["time"] = now
            return rates
        else:
            print("❌ هیچ نرخی استخراج نشد. کلیدهای موجود در current:", list(current.keys())[:20])
    except requests.exceptions.RequestException as e:
        print("❌ خطای شبکه در گرفتن قیمت ارز (احتمالا فایروال سرور یا قطعی اینترنت):", e)
    except Exception as e:
        print("❌ خطای غیرمنتظره در گرفتن قیمت ارز:", e)
    return CURRENCY_CACHE["data"]


async def handle_currency_query(message, text_raw):
    match = re.search(r'(\d+(?:[.,]\d+)?)\s*(دلار|یورو|یوان|پوند|درهم|لیر)', text_raw)
    if not match:
        return False

    amount = float(match.group(1).replace(",", "."))
    currency_fa = match.group(2)

    rates = fetch_currency_rates()
    if not rates or currency_fa not in rates:
        await bot_reply(message, "❌ الان نمی‌تونم قیمت لحظه‌ای ارز رو بگیرم، یکم بعد دوباره امتحان کن.")
        return True

    price_per_unit = rates[currency_fa]
    total = amount * price_per_unit
    await bot_reply(
        message,
        f"💵 قیمت لحظه‌ای هر {currency_fa}: {price_per_unit:,.0f} تومان\n\n"
        f"🔢 {amount:,.0f} {currency_fa} = {total:,.0f} تومان 💰"
    )
    return True


# ---------------------------------------------------------------------------
# منطق بازی پنالتی (کاملا متنی، بدون دکمه)
# ---------------------------------------------------------------------------
async def render_penalty_prompt(message):
    lines = [f"{i+1}️⃣ {label}" for i, (_, label) in enumerate(PENALTY_ZONES)]
    text = ("⚽ آماده‌ای؟ توپ رو به کدوم گوشه می‌زنی؟\n\n" + "\n".join(lines) +
            "\n\n🔢 عدد گوشه مورد نظرتو بفرست (۱ تا ۶)\n🏁 برای پایان بازی بنویس: پایان")
    await bot_reply(message, text)


def take_penalty(u, zone_id):
    items = u.get("penalty_items", [])
    if "توپ آتشین" in items and random.random() < 0.10:
        return True, "curve"

    zones = [z[0] for z in PENALTY_ZONES]
    if "ستاره شانس" in items and random.random() < 0.15:
        keeper_pick = random.choice([z for z in zones if z != zone_id])
    else:
        keeper_pick = random.choice(zones)

    if keeper_pick != zone_id:
        return True, "normal"

    if "کفش ویژه" in items and random.random() < 0.20:
        return True, "rebound"

    return False, "save"


async def handle_penalty_input(message, uid, u, text_raw):
    if text_raw in ("پایان", "پایان بازی", "پایان پنالتی"):
        sess = active_penalty.pop(uid, {"shots": 0, "goals": 0})
        await bot_reply(message, f"🏁 پایان بازی پنالتی!\n\n⚽ نتیجه نهایی: {sess['goals']} گل از {sess['shots']} شوت\n\nبرای شروع دوباره بنویس: پنالتی")
        return

    if not (text_raw.isdigit() and 1 <= int(text_raw) <= len(PENALTY_ZONES)):
        await bot_reply(message, "❌ لطفاً یه عدد بین ۱ تا ۶ بفرست، یا برای پایان بازی بنویس «پایان»")
        return

    zone_id = PENALTY_ZONES[int(text_raw) - 1][0]
    sess = active_penalty.setdefault(uid, {"shots": 0, "goals": 0})
    sess["shots"] += 1

    goal, kind = take_penalty(u, zone_id)
    p = u["penalty"]

    if goal:
        sess["goals"] += 1
        p["goals"] += 1
        p["streak"] += 1
        p["best_streak"] = max(p["best_streak"], p["streak"])
        coin_reward = 15
        for item, bonus in PENALTY_COIN_BONUS.items():
            if item in u["penalty_items"]:
                coin_reward += bonus
        xp_reward = 10
        if "توپ الماسی" in u["penalty_items"] or "مدال قهرمانی" in u["penalty_items"]:
            xp_reward += 5
        add_coins(uid, coin_reward)
        add_xp(uid, xp_reward)
        flavor = {
            "normal": "⚽ گـــل! دروازه‌بان اشتباه پرید!",
            "curve": "🔥 یه شوت فرم‌دار محشر! غیرقابل‌دفاع بود!",
            "rebound": "🎯 دروازه‌بان گرفت ولی توپ برگشت تو دروازه! گل!",
        }[kind]
        await bot_reply(message, f"{flavor}\n💰 +{coin_reward} سکه | ✨ +{xp_reward} XP\n(گل‌های این بازی: {sess['goals']}/{sess['shots']})\n\n🔢 برای شوت بعدی عدد ۱ تا ۶ رو بفرست یا بنویس «پایان»")
    else:
        p["misses"] += 1
        p["streak"] = 0
        await bot_reply(message, f"🧤 دروازه‌بان گرفتش! حیف شد...\n(گل‌های این بازی: {sess['goals']}/{sess['shots']})\n\n🔢 برای شوت بعدی عدد ۱ تا ۶ رو بفرست یا بنویس «پایان»")
    save_data()


# ---------------------------------------------------------------------------
# منطق بازی فرار از زندان (کاملا متنی، بدون دکمه)
# ---------------------------------------------------------------------------
async def render_or_finish_prison(message, uid, u, node_id):
    node = PRISON_NODES.get(node_id)
    if node is None:
        return

    if "options" in node:
        opt_map = {}
        lines = []
        for i, (opt_id, label) in enumerate(node["options"]):
            opt_map[str(i + 1)] = opt_id
            lines.append(f"{i+1}️⃣ {label}")
        active_prison[uid] = {"node": node_id, "map": opt_map}
        await bot_reply(message, node["text"] + "\n\n" + "\n".join(lines) + "\n\n🔢 عدد گزینه مورد نظرتو بفرست")
        return

    if "chance" in node:
        won = random.random() < node["chance"]
        text = node["win_text"] if won else node["lose_text"]
    else:
        won = node.get("outcome") == "win"
        text = node["text"]

    active_prison.pop(uid, None)

    if won:
        coins_reward = random.randint(80, 150)
        xp_reward = 25
        add_coins(uid, coins_reward)
        add_xp(uid, xp_reward)
        u["prison"]["wins"] += 1
        await bot_reply(message, f"{text}\n\n💰 +{coins_reward} سکه | ✨ +{xp_reward} XP")
    else:
        lost_coins = min(u["coins"], random.randint(10, 30))
        u["coins"] -= lost_coins
        u["prison"]["losses"] += 1
        await bot_reply(message, f"{text}\n\n💸 {lost_coins} سکه از دست دادی (جریمه)")
    save_data()


async def handle_prison_input(message, uid, u, text_raw):
    session = active_prison.get(uid)
    if not session:
        return
    choice = session["map"].get(text_raw)
    if not choice:
        await bot_reply(message, "❌ لطفاً یکی از عددهای نمایش داده‌شده رو بفرست")
        return
    await render_or_finish_prison(message, uid, u, choice)


# ---------------------------------------------------------------------------
# منطق بازی جرعت حقیقت 🎭
# ---------------------------------------------------------------------------
async def start_truth_dare(message, uid):
    active_truth_dare[uid] = True
    await bot_reply(message, "🎭 جرعت یا حقیقت؟ یکیشو انتخاب کن!\n(بنویس «جرعت» یا «حقیقت» — برای پایان بازی بنویس «پایان»)")


async def handle_truth_dare_input(message, uid, text_raw):
    if text_raw in ("پایان", "پایان بازی"):
        active_truth_dare.pop(uid, None)
        await bot_reply(message, "🏁 بازی جرعت حقیقت تموم شد! برای شروع دوباره بنویس «جرعت حقیقت»")
        return
    if "حقیقت" in text_raw:
        await bot_reply(message, f"🤫 حقیقت:\n{random.choice(TRUTHS)}\n\nبرای دور بعد بنویس «جرعت» یا «حقیقت»، یا برای پایان بنویس «پایان»")
    elif "جرعت" in text_raw or "جرات" in text_raw:
        await bot_reply(message, f"🔥 جرعت:\n{random.choice(DARES)}\n\nبرای دور بعد بنویس «جرعت» یا «حقیقت»، یا برای پایان بنویس «پایان»")
    else:
        await bot_reply(message, "❓ بنویس «جرعت» یا «حقیقت»، یا برای پایان بنویس «پایان»")


# ---------------------------------------------------------------------------
# بازی کوتاه و خنده‌دار: دروغ‌سنج 🕵️
# ---------------------------------------------------------------------------
async def start_lie_detector(message, uid):
    active_lie_detector.add(uid)
    q = random.choice(LIE_DETECTOR_QUESTIONS)
    await bot_reply(message, f"🕵️ دستگاه دروغ‌سنج روشن شد!\n\n❓ {q}\n\n(هرچی می‌خوای جواب بده، دستگاه خودش تشخیص میده 😏)")


async def handle_lie_detector_input(message, uid, text_raw):
    active_lie_detector.discard(uid)
    percent = random.randint(0, 100)
    if percent < 30:
        verdict = "😇 راستشو گفتی! دستگاه تاییدت کرد."
    elif percent < 70:
        verdict = "🤨 یه چیزی مشکوکه... شاید نصفه‌راستشو گفتی!"
    else:
        verdict = "🤥 چراغا قرمز شد! صد در صد داری دروغ میگی!"
    await bot_reply(message, f"🕵️ نتیجه دستگاه دروغ‌سنج:\n📊 درصد دروغ: {percent}٪\n\n{verdict}\n\nبرای دوباره بازی کردن بنویس «دروغ سنج»")


# ---------------------------------------------------------------------------
# ذخیره و بازیابی اطلاعات (تا با ری‌استارت شدن ربات چیزی از دست نره)
# ---------------------------------------------------------------------------
def save_data():
    try:
        data = {
            "users": users,
            "locks": locks,
            "registered_groups": registered_groups,
            "warn_counts": warn_counts,
        }
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception as e:
        print("خطا در ذخیره دیتا:", e)


def load_data():
    global users, locks, registered_groups, warn_counts
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        users.update(data.get("users", {}))
        locks.update(data.get("locks", {}))
        registered_groups.update(data.get("registered_groups", {}))
        warn_counts.update(data.get("warn_counts", {}))
        print(f"✅ دیتا بارگذاری شد: {len(users)} کاربر")
    except FileNotFoundError:
        print("ℹ️ فایل دیتا هنوز وجود نداره، از صفر شروع می‌کنیم.")
    except Exception as e:
        print("خطا در بارگذاری دیتا:", e)


@bot.on_message()
async def start_handler(bot: Robot, message: Message):
    dedupe_id = getattr(message, "message_id", None)
    if dedupe_id:
        if dedupe_id in processed_message_ids:
            print("⏭️ پیام تکراری نادیده گرفته شد:", dedupe_id)
            return
        processed_message_ids.add(dedupe_id)
        if len(processed_message_ids) > MAX_PROCESSED_IDS:
            processed_message_ids.clear()

    print("chat_id:", message.chat_id, "| text:", message.text)

    text_raw = (message.text or "").strip()
    text = text_raw.lower()
    chat_id = message.chat_id
    uid = get_uid(message)

    msg_id = getattr(message, "message_id", None)
    if msg_id:
        message_senders[msg_id] = uid
        if len(message_senders) > 5000:
            message_senders.clear()

    reply_to_id = getattr(message, "reply_to_message_id", None)
    if reply_to_id:
        if reply_to_id in bot_message_ids:
            pass
        elif reply_to_id in message_senders:
            return

    if text_raw == "/start":
        await bot_reply(message, f"""🌟═══════════════════════🌟
     👑 به دنیای «{BOT_BRAND}» خوش اومدی 👑
🌟═══════════════════════🌟

🫡 من پرسیام؛ دستیار باهوش، سرگرم‌کننده و همیشه‌بیدارِ این گروه!
از بازی و اقتصاد گرفته تا امنیت و آمار حرفه‌ای، همه‌چی زیر یک سقفه 🏯

✨ چند نمونه از کارایی که بلدم:
🎮 بازی‌های متنوع: دوز، حدس عدد، پنالتی، فرار از زندان، جرعت حقیقت، دروغ‌سنج
💰 اقتصاد کامل: سکه، جایزه روزانه، فروشگاه، شکار موجودات
🧮 ماشین‌حساب متنی: فقط بنویس مثلا «5 + 3» یا «10 ضرب در 2»
💱 قیمت لحظه‌ای ارز: بنویس مثلا «1000 دلار به تومان»
📊 پروفایل اختصاصی: لقب، اسم و ایموجی دلخواه خودت
🛡️ امنیت گروه: چند نوع قفل هوشمند برای محافظت از گروهت

📜 برای دیدن لیست کامل دستورات بنویس:
👉 قابلیت ها

👑 برای شناخت سازنده‌ام بنویس: مالک ربات

بزن بریم که خوش بگذره رفیق! 🚀""")
        return

    u = get_user(uid)
    u["chat_id"] = chat_id
    if not is_group(chat_id):
        u["pv_chat_id"] = chat_id
    u["messages"] += 1
    update_message_counters(u)

    chat_history.setdefault(chat_id, []).append(text_raw)
    if len(chat_history[chat_id]) > 50:
        chat_history[chat_id] = chat_history[chat_id][-50:]

    grp_locks = get_locks(chat_id)
    is_admin_or_owner = is_bot_admin(uid) or is_owner(chat_id, uid)

    if is_group(chat_id) and not is_admin_or_owner:
        if grp_locks.get("link", True):
            if "http://" in text or "https://" in text or "t.me/" in text or "rubika.ir/" in text:
                deleted = await try_delete_message(chat_id, msg_id)
                if deleted:
                    await bot_reply(message, "🔗 لینک ارسالی‌ات به دلیل فعال بودن قفل لینک، حذف شد.")
                else:
                    await bot_reply(message, "🔗 ارسال لینک در این گروه غیرمجازه (قفل لینک فعاله)! لطفاً از ارسال لینک خودداری کن.")
                return

        if grp_locks.get("badword", True) and BADWORDS:
            if any(bw in text for bw in BADWORDS):
                await handle_violation(message, chat_id, uid, "استفاده از الفاظ نامناسب")
                return

        if grp_locks.get("mention", True):
            if text_raw.count("@") >= 4:
                await handle_violation(message, chat_id, uid, "منشن دادن بیش‌ازحد")
                return

        if grp_locks.get("forward", True):
            if is_forwarded_message(message):
                await handle_violation(message, chat_id, uid, "فوروارد کردن پیام")
                return

        if grp_locks.get("spam", True):
            now = datetime.now().timestamp()
            spam_tracker.setdefault(uid, [])
            spam_tracker[uid] = [t for t in spam_tracker[uid] if now - t < 10]
            spam_tracker[uid].append(now)
            if len(spam_tracker[uid]) > 6:
                await handle_violation(message, chat_id, uid, "اسپم زیاد")
                spam_tracker[uid] = []
                return

    if uid in active_guess:
        if text.isdigit():
            guess = int(text)
            answer = active_guess[uid]
            if guess == answer:
                add_coins(uid, 15)
                add_xp(uid, 10)
                u["wins"] += 1
                await bot_reply(message, f"🎉 درست حدس زدی ({answer})!\n+10 XP و +15 سکه گرفتی")
                del active_guess[uid]
                save_data()
            elif guess < answer:
                await bot_reply(message, "⬆️ عدد بزرگتره")
            else:
                await bot_reply(message, "⬇️ عدد کوچیک‌تره")
            return

    if uid in active_tictactoe and text.isdigit() and 1 <= int(text) <= 9:
        game = active_tictactoe[uid]
        pos = int(text) - 1
        if game["board"][pos] != " ":
            await bot_reply(message, "❌ این خونه پره، یکی دیگه رو انتخاب کن")
            return
        game["board"][pos] = "X"

        def check_win(b, p):
            wins = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]
            return any(b[a] == b[c] == b[d] == p for a, c, d in wins)

        def render(b):
            return "\n---------\n".join(" | ".join(b[i:i + 3]) for i in range(0, 9, 3))

        if check_win(game["board"], "X"):
            add_coins(uid, 20)
            add_xp(uid, 15)
            u["wins"] += 1
            await bot_reply(message, f"🎉 بردی!\n{render(game['board'])}\n+15 XP و +20 سکه")
            del active_tictactoe[uid]
            save_data()
            return

        if " " not in game["board"]:
            await bot_reply(message, f"🤝 مساوی شد!\n{render(game['board'])}")
            del active_tictactoe[uid]
            return

        empty = [i for i, v in enumerate(game["board"]) if v == " "]
        bot_move = random.choice(empty)
        game["board"][bot_move] = "O"

        if check_win(game["board"], "O"):
            await bot_reply(message, f"🤖 من بردم! دفعه بعد بهتر بازی کن\n{render(game['board'])}")
            del active_tictactoe[uid]
            return

        if " " not in game["board"]:
            await bot_reply(message, f"🤝 مساوی شد!\n{render(game['board'])}")
            del active_tictactoe[uid]
            return

        await bot_reply(message, f"{render(game['board'])}\n\nنوبت توئه، عدد خونه (1-9) رو بفرست")
        return

    if uid in active_penalty and (text_raw.isdigit() or text_raw in ("پایان", "پایان بازی", "پایان پنالتی")):
        await handle_penalty_input(message, uid, u, text_raw)
        return

    if uid in active_prison and text_raw.isdigit():
        await handle_prison_input(message, uid, u, text_raw)
        return

    if uid in active_truth_dare:
        await handle_truth_dare_input(message, uid, text_raw)
        return

    if uid in active_lie_detector:
        await handle_lie_detector_input(message, uid, text_raw)
        return

    if await handle_currency_query(message, text_raw):
        return

    if await handle_math_query(message, text_raw):
        return

    if "سلام" in text or "درود" in text or "هی" in text or "های" in text:
        await bot_reply(message, random.choice(GREETINGS))

    elif "خوبی" in text or "چطوری" in text or "حالت" in text:
        await bot_reply(message, random.choice(HOW_ARE_YOU))

    elif "صبح بخیر" in text:
        await bot_reply(message, "☀️ صبح بخیر رفیق، امیدوارم امروز روز پر از خیر و برکتی برات باشه.")

    elif "شب بخیر" in text:
        await bot_reply(message, "🌙 شب بخیر عزیز، خوابای قشنگ ببینی و فردا با انرژی بیدار شی.")

    elif "مرسی" in text or "ممنون" in text:
        await bot_reply(message, random.choice(THANKS_REPLIES))

    elif "خدافظ" in text or "فعلا" in text:
        await bot_reply(message, random.choice(GOODBYE_REPLIES))

    elif "جوک" in text:
        await bot_reply(message, random.choice(JOKES))

    elif "شانس" in text and "گردونه" not in text:
        luck, first_time = get_daily_luck(u)
        if first_time:
            await bot_reply(message, f"🍀 شانس امروزت: {luck}٪")
        else:
            await bot_reply(message, f"🍀 قبلاً گفته بودم بهت، شانس امروزت {luck}٪ هست 😄")

    elif "فال" in text:
        await bot_reply(message, random.choice(["✨ امروز روز خوبیه.", "🍀 یه خبر خوب در راهه.", "😎 موفق میشی، ادامه بده.", "💎 یه اتفاق جالب منتظرته."]))

    elif "تاس" in text:
        await bot_reply(message, f"🎲 عددت: {random.randint(1,6)}")

    elif "شیر یا خط" in text:
        await bot_reply(message, random.choice(["🪙 شیر", "🪙 خط"]))

    elif "سنگ کاغذ قیچی" in text:
        await bot_reply(message, random.choice(["✊ سنگ", "✋ کاغذ", "✌️ قیچی"]))

    elif "ساعت" in text:
        await bot_reply(message, f"🕒 ساعت الان: {datetime.now().strftime('%H:%M:%S')}")

    elif "تاریخ" in text:
        now = datetime.now()
        await bot_reply(message, f"📅 تاریخ:\n🇮🇷 شمسی: {get_jalali_date_str()}\n🌍 میلادی: {now.strftime('%Y/%m/%d')}\n🕒 ساعت: {now.strftime('%H:%M:%S')}")

    elif text.startswith("انتخاب کن"):
        options = [o.strip() for o in text.replace("انتخاب کن", "").strip().split(" یا ") if o.strip()]
        if len(options) >= 2:
            await bot_reply(message, f"🎯 من انتخاب می‌کنم: {random.choice(options)}")
        else:
            await bot_reply(message, "بنویس: «انتخاب کن پیتزا یا برگر»")

    elif text_raw.startswith("تنظیم اسم"):
        val = text_raw.replace("تنظیم اسم", "", 1).strip()
        if not val:
            await bot_reply(message, "بنویس: «تنظیم اسم [نام دلخواهت]»")
        else:
            u["nickname"] = val
            save_data()
            await bot_reply(message, f"✅ اسم نمایشیت تنظیم شد: {val}\nاین اسم از الان تو «پروفایل» و «آمار» نشون داده میشه.")

    elif text_raw.startswith("تنظیم ایموجی"):
        val = text_raw.replace("تنظیم ایموجی", "", 1).strip()
        if not val:
            await bot_reply(message, "بنویس: «تنظیم ایموجی 🐉» (فقط یه شکلک بفرست)")
        else:
            u["custom_emoji"] = val
            save_data()
            await bot_reply(message, f"✅ ایموجی اختصاصیت تنظیم شد: {val}")

    elif "پروفایل" in text:
        name = await resolve_display_name(bot, message, uid, u)
        emoji = resolve_emoji(u, uid)
        await bot_reply(message, f"""👤 پروفایل تو {emoji}

📛 اسم: {name}
⭐ سطح: {get_level(u['xp'])}
✨ XP: {u['xp']}
💰 سکه: {u['coins']}
🏅 مدال: {get_badge(u['xp'])}
🎮 بازی‌ها: {u['games']}
✅ بردها: {u['wins']}
💬 پیام‌ها: {u['messages']}
🔥 استریک روزانه: {u['streak']}
🎒 آیتم‌ها: {", ".join(u['items']) if u['items'] else "چیزی نداری"}
⚽ آیتم‌های پنالتی: {", ".join(u['penalty_items']) if u['penalty_items'] else "چیزی نداری"}
🐉 موجودات: {", ".join(u['creatures']) if u['creatures'] else "چیزی نداری"}

💡 برای شخصی‌سازی: «تنظیم اسم [نام]» یا «تنظیم ایموجی [شکلک]»""")

    elif "امار" in text or "آمار" in text:
        name = await resolve_display_name(bot, message, uid, u)
        emoji = resolve_emoji(u, uid)
        title = u["title"] if u["title"] else "بدون لقب"
        origin = u["origin"] if u["origin"] else "بدون اصل"
        rank_label = "مالک 👑" if is_owner(chat_id, uid) else "عضو"
        warn_count = warn_counts.get(f"{chat_id}|{uid}", 0)
        today_count = u["msg_daily"]["count"] if u["msg_daily"]["date"] == date.today().isoformat() else 0
        level = get_level(u["xp"])
        xp_in_level = u["xp"] % 100
        bar = progress_bar(xp_in_level, 100)
        p = u["penalty"]
        pr = u["prison"]
        leaderboard_pos = get_rank_position(uid)

        await bot_reply(message, f"""╔════════✦ آمار کاربری ✦════════╗
     {emoji}  {name}
╚═══════════════════════════╝

🏷 لقب: {title}
🌍 اصل: {origin}
👑 مقام: {rank_label}
🏆 رتبه در جدول برترین‌ها: {leaderboard_pos}

⭐ سطح {level}  |  ✨ {u['xp']} XP
{bar}  {xp_in_level}/100
💰 سکه: {u['coins']}   🏅 {get_badge(u['xp'])}

━━━━━━━━━━━━━━━━
🎮 بازی‌ها
━━━━━━━━━━━━━━━━
🕹 کل بازی‌ها: {u['games']}   ✅ بردها: {u['wins']}
⚽ پنالتی: {p['goals']} گل | {p['misses']} از دست‌رفته | بهترین سری: {p['best_streak']}
🚔 فرار از زندان: {pr['wins']} برد | {pr['losses']} باخت

━━━━━━━━━━━━━━━━
💬 پیام‌ها
━━━━━━━━━━━━━━━━
کل: {u['messages']}  |  امروز: {today_count}
این هفته: {u['msg_weekly']['count']}  |  این ماه: {u['msg_monthly']['count']}

⚠️ اخطارها: {warn_count}
📅 {get_jalali_date_str()}

💡 با «تنظیم اسم» و «تنظیم ایموجی» ظاهر پروفایلتو شخصی‌سازی کن""")

    elif text_raw.startswith("تنظیم لقب"):
        val = text_raw.replace("تنظیم لقب", "", 1).strip()
        if not val:
            await bot_reply(message, "بنویس: «تنظیم لقب [متن]»")
        else:
            u["title"] = val
            save_data()
            await bot_reply(message, f"✅ لقبت تنظیم شد: {val}")

    elif text_raw.startswith("تنظیم اصل"):
        val = text_raw.replace("تنظیم اصل", "", 1).strip()
        if not val:
            await bot_reply(message, "بنویس: «تنظیم اصل [متن]»")
        else:
            u["origin"] = val
            save_data()
            await bot_reply(message, f"✅ اصلت تنظیم شد: {val}")

    elif "چالش" in text:
        await bot_reply(message, f"🎯 چالش:\n\n{random.choice(CHALLENGES)}")

    elif "پرسیا" in text:
        await bot_reply(message, random.choice(["جانم؟ 😄", "بله در خدمتم 🙌", "پرسیا اینجاست 😎", "جونم بگو 😄"]))

    elif text_raw in ("ایدی من", "آیدی من", "ایدیم", "آیدیم"):
        await bot_reply(message, f"🆔 chat_id: {chat_id}\n🆔 uid (این رو تو ADMIN_ID بذار): {uid}")

    elif "معرفی مالک" in text or "مالک ربات" in text or text_raw in ("مالک", "سازنده"):
        await bot_reply(message, f"""👑 معرفی مالک ربات {BOT_BRAND}

🆔 یوزرنیم: {OWNER_USERNAME}
🔗 لینک پروفایل: {OWNER_LINK}
ما تلاشمون اینه بهترینو بسازیم امیدوارم خوشتون بیاد اگه باز میگم اکه مشکلی پیش اومده یا هرچیز دیگه ای بگید تا مشکلشو برطرف کنم 
این ربات با افتخار توسط ایشون طراحی و توسعه داده شده 🛠️
هر پیشنهاد یا انتقادی داشتی مستقیم به ایشون پیام بده 🙌""")

    elif "امتیاز من" in text or "امتیازم" in text:
        await bot_reply(message, f"🏆 XP تو: {u['xp']} (سطح {get_level(u['xp'])})")

    elif text == "کاربران":
        await bot_reply(message, f"👥 تعداد کل کاربرانی که به این ربات پیام دادن: {len(users)}")

    elif "جایزه روزانه" in text or ("جایزه" in text and "گردونه" not in text):
        today = date.today().isoformat()
        if u["last_daily"] == today:
            await bot_reply(message, "⏳ امروز جایزه‌تو گرفتی، فردا دوباره بیا!")
        else:
            yesterday = (date.today() - timedelta(days=1)).isoformat() if u["last_daily"] else None
            u["streak"] = u["streak"] + 1 if u["last_daily"] == yesterday else 1
            u["last_daily"] = today
            reward_coins = 50 + (u["streak"] * 5)
            add_coins(uid, reward_coins)
            add_xp(uid, 10)
            save_data()
            await bot_reply(message, f"🎁 جایزه روزانه گرفتی!\n💰 +{reward_coins} سکه | ✨ +10 XP\n🔥 استریک: {u['streak']} روز")

    elif "گردونه" in text:
        cost = 20
        if u["coins"] < cost:
            await bot_reply(message, f"❌ سکه کافی نداری (نیاز: {cost} سکه)")
        else:
            u["coins"] -= cost
            prize = random.choice([0, 10, 20, 50, 100, 200])
            if prize == 0:
                await bot_reply(message, "😅 هیچی نبردی! دوباره امتحان کن")
            else:
                add_coins(uid, prize)
                await bot_reply(message, f"🎰 گردونه چرخید... 🎉 بردی: {prize} سکه!")
            save_data()

    elif text.startswith("شرط"):
        parts = text.split()
        if len(parts) >= 2 and parts[1].isdigit():
            bet = int(parts[1])
            if bet <= 0:
                await bot_reply(message, "❌ مقدار شرط باید بیشتر از صفر باشه")
            elif u["coins"] < bet:
                await bot_reply(message, "❌ سکه کافی نداری")
            else:
                u["coins"] -= bet
                if random.random() < 0.5:
                    win = bet * 2
                    add_coins(uid, win)
                    await bot_reply(message, f"🎉 بردی! {win} سکه گرفتی")
                else:
                    await bot_reply(message, f"😢 باختی! {bet} سکه از دست دادی")
                save_data()
        else:
            await bot_reply(message, "بنویس: «شرط [مقدار سکه]» مثلاً «شرط 50»")

    elif "شکار" in text:
        if random.random() < 0.4:
            creature = random.choice(CREATURES)
            u["creatures"].append(creature)
            save_data()
            await bot_reply(message, f"🎉 یه {creature} گرفتی! برای دیدن موجوداتت بنویس «پروفایل»")
        else:
            await bot_reply(message, "😅 چیزی پیدا نکردی، دوباره امتحان کن")

    elif "فروشگاه پنالتی" in text:
        shop_list = "\n".join([f"{PENALTY_EMOJI[name]} {name} - {price:,} سکه" for name, price in PENALTY_SHOP.items()])
        await bot_reply(message, f"""🏟 فروشگاه ویژه پنالتی

{shop_list}

🥇 توپ طلایی: هر گل +5 سکه اضافه
🔥 توپ آتشین: شانس شوت فرم‌دار غیرقابل‌دفاع
👟 کفش ویژه: شانس گل از روی برگشت توپ
⭐ ستاره شانس: افزایش شانس اشتباه رفتن دروازه‌بان
💨 کفش سرعتی: هر گل +8 سکه اضافه
💎 توپ الماسی: هر گل +15 سکه و +5 XP اضافه
🏆 مدال قهرمانی: هر گل +25 سکه و +5 XP اضافه (نهایت پرستیژ!)

برای خرید بنویس: «خرید پنالتی [نام آیتم]»""")

    elif text.startswith("خرید پنالتی"):
        item_name = text.replace("خرید پنالتی", "").strip()
        matched = next((name for name in PENALTY_SHOP if name in item_name), None)
        if not matched:
            await bot_reply(message, "❌ این آیتم تو فروشگاه پنالتی نیست")
        elif u["coins"] < PENALTY_SHOP[matched]:
            await bot_reply(message, f"❌ سکه کافی نداری (نیاز: {PENALTY_SHOP[matched]:,} سکه، داری: {u['coins']:,} سکه)")
        elif matched in u["penalty_items"]:
            await bot_reply(message, "✅ این آیتمو قبلاً خریدی")
        else:
            u["coins"] -= PENALTY_SHOP[matched]
            u["penalty_items"].append(matched)
            save_data()
            await bot_reply(message, f"✅ {PENALTY_EMOJI[matched]} {matched} خریداری شد! 🎉")

    elif "فروشگاه" in text:
        shop_list = "\n".join([f"🛒 {name} - {price:,} سکه" for name, price in SHOP_ITEMS.items()])
        await bot_reply(message, f"🏪 فروشگاه:\n\n{shop_list}\n\nبرای خرید بنویس: «خرید [نام آیتم]»")

    elif text.startswith("خرید"):
        item_name = text.replace("خرید", "").strip()
        matched = next((name for name in SHOP_ITEMS if name in item_name), None)
        if not matched:
            await bot_reply(message, "❌ این آیتم تو فروشگاه نیست")
        elif u["coins"] < SHOP_ITEMS[matched]:
            await bot_reply(message, f"❌ سکه کافی نداری (نیاز: {SHOP_ITEMS[matched]:,} سکه، داری: {u['coins']:,} سکه)")
        elif matched in u["items"]:
            await bot_reply(message, "✅ این آیتمو قبلاً خریدی")
        else:
            u["coins"] -= SHOP_ITEMS[matched]
            u["items"].append(matched)
            save_data()
            await bot_reply(message, f"✅ {matched} خریداری شد! 🎉")

    elif "حدس عدد" in text or "بازی حدس" in text:
        active_guess[uid] = random.randint(1, 50)
        u["games"] += 1
        await bot_reply(message, "🎮 یه عدد بین ۱ تا ۵۰ تو ذهنم دارم. حدس بزن!")

    elif text == "دوز":
        active_tictactoe[uid] = {"board": [" "] * 9}
        u["games"] += 1
        await bot_reply(message, "❌⭕ بازی دوز شروع شد! تو X هستی، من O هستم.\nخونه‌ها از ۱ تا ۹ شماره‌گذاری شدن\nعدد خونه مورد نظرت رو بفرست")

    elif text == "پنالتی" or text.startswith("پنالتی"):
        active_penalty[uid] = {"shots": 0, "goals": 0}
        u["games"] += 1
        await render_penalty_prompt(message)

    elif "فرار از زندان" in text or "فرار زندان" in text:
        u["games"] += 1
        await render_or_finish_prison(message, uid, u, "start")

    elif "جرعت حقیقت" in text or "جرات حقیقت" in text or "جرات یا حقیقت" in text or "جرعت یا حقیقت" in text:
        u["games"] += 1
        await start_truth_dare(message, uid)

    elif text_raw in ("دروغ سنج", "دروغ‌سنج"):
        u["games"] += 1
        await start_lie_detector(message, uid)

    elif "معما" in text:
        q, a = random.choice(RIDDLES)
        await bot_reply(message, f"🧩 معما:\n{q}")

    elif "مسابقه" in text:
        q, a = random.choice(QUIZ)
        await bot_reply(message, f"📝 سوال:\n{q}")

    elif "شروع قرعه کشی" in text or "شروع قرعه‌کشی" in text:
        lottery["open"] = True
        lottery["participants"] = []
        await bot_reply(message, "🎲 قرعه‌کشی شروع شد! برای شرکت بنویس «شرکت»")

    elif text == "شرکت":
        if not lottery["open"]:
            await bot_reply(message, "❌ الان قرعه‌کشی فعالی وجود نداره")
        elif uid in lottery["participants"]:
            await bot_reply(message, "✅ تو قبلاً شرکت کردی")
        else:
            lottery["participants"].append(uid)
            await bot_reply(message, f"✅ شرکت کردی! (تعداد شرکت‌کننده‌ها: {len(lottery['participants'])})")

    elif "برنده قرعه کشی" in text or "برنده قرعه‌کشی" in text:
        if not lottery["open"] or not lottery["participants"]:
            await bot_reply(message, "❌ شرکت‌کننده‌ای وجود نداره")
        else:
            winner = random.choice(lottery["participants"])
            add_coins(winner, 100)
            lottery["open"] = False
            save_data()
            await bot_reply(message, "🎉 برنده قرعه‌کشی مشخص شد و ۱۰۰ سکه گرفت!")

    elif "رتبه" in text or "برترین" in text:
        top = sorted(users.items(), key=lambda x: x[1]["xp"], reverse=True)[:5]
        if not top:
            await bot_reply(message, "هنوز کسی امتیازی نداره")
        else:
            board = "\n".join([f"{i+1}. سطح {get_level(d['xp'])} - {d['xp']} XP" for i, (_, d) in enumerate(top)])
            await bot_reply(message, f"🥇 جدول برترین‌ها:\n\n{board}")

    elif "تاریخچه" in text:
        hist = chat_history.get(chat_id, [])[-10:]
        await bot_reply(message, ("🧾 ۱۰ پیام آخر:\n\n" + "\n".join(hist)) if hist else "چیزی ثبت نشده")

    elif text == "فعال":
        if chat_id in registered_groups:
            await bot_reply(message, "ℹ️ این گروه قبلاً فعال شده.")
        else:
            registered_groups[chat_id] = {"owner": uid}
            save_data()
            await bot_reply(message, "✅ گروه فعال شد و شما به عنوان مالک این گروه (نزد ربات) ثبت شدید.\nفقط شما می‌تونی قفل‌ها رو تغییر بدی.")

    elif "لیست قفل" in text:
        lines = []
        for key, label in LOCK_LABELS.items():
            status = "🔒 قفل" if grp_locks.get(key, True) else "🔓 باز"
            lines.append(f"{LOCK_ICONS[key]} {label}: {status}")
        await bot_reply(message, "🔐 وضعیت قفل‌های امنیتی این گروه:\n\n" + "\n".join(lines))

    elif text.startswith("قفل") or "باز کردن قفل" in text or "بازکردن قفل" in text:
        if chat_id not in registered_groups:
            await bot_reply(message, "⛔ اول باید تو گروه بنویسی «فعال» تا ثبت بشه.")
        elif not is_owner(chat_id, uid) and not is_bot_admin(uid):
            await bot_reply(message, "⛔ فقط مالک گروه (کسی که «فعال» رو زده) می‌تونه قفل‌ها رو تغییر بده.")
        else:
            is_unlock = "باز" in text
            matched_key = None
            for key, label in LOCK_LABELS.items():
                if label in text:
                    matched_key = key
                    break
            if not matched_key:
                names = "، ".join(LOCK_LABELS.values())
                await bot_reply(message, f"بنویس: «قفل [نوع]» یا «باز کردن قفل [نوع]»\nانواع قفل: {names}")
            else:
                grp_locks[matched_key] = not is_unlock
                save_data()
                await bot_reply(message, f"{'🔓 باز شد' if is_unlock else '🔒 فعال شد'}: {LOCK_ICONS[matched_key]} {LOCK_LABELS[matched_key]}")

    elif "خبر" in text and "چه" in text:
        await bot_reply(message, random.choice(["سلامتی 😄", "همه چی خوبه 🙌", "خبر خاصی نیست 😅"]))

    elif "کجایی" in text:
        await bot_reply(message, random.choice(["تو گوشیتم 😄", "همینجا کنارتم تو چت 📱"]))

    elif "اسمت چیه" in text or "اسمت" in text:
        await bot_reply(message, random.choice(INTRO_REPLIES))

    elif "چند سالته" in text:
        await bot_reply(message, random.choice(["سنی ندارم، من یه رباتم 🤖", "ربات‌ها سن ندارن دادا 😄"]))

    elif "کی ساختت" in text or "سازندت" in text:
        await bot_reply(message, random.choice(["صاحبم منو ساخته 😄 اگه بخوای بشناسیش بنویس «مالک ربات»", "یه برنامه‌نویس باحال منو ساخته 👨‍💻 برای شناخت بیشتر بنویس «مالک ربات»"]))

    elif "دمت گرم" in text or "لطف کردی" in text:
        await bot_reply(message, random.choice(["خواهش می‌کنم داداش ❤️", "قربونت، وظیفه‌ست 🙏"]))

    elif "خواهش می‌کنم" in text or "خواهش میکنم" in text:
        await bot_reply(message, random.choice(["لطف داری 🙏", "خودتی داداش ❤️"]))

    elif "ببخشید" in text or "معذرت" in text:
        await bot_reply(message, random.choice(["عیبی نداره 😊", "مشکلی نیست، راحت باش 🙂"]))

    elif "خسته نباشی" in text:
        await bot_reply(message, random.choice(["سلامت باشی 🙏", "ممنون، تو هم خسته نباشی 😄"]))

    elif "خوش اومدی" in text:
        await bot_reply(message, random.choice(["ممنون 😄", "خیلی ممنون ازت ❤️"]))

    elif "کمکم کن" in text:
        await bot_reply(message, random.choice(["بگو چیکار داری 😊", "در خدمتم، بگو مشکلت چیه 🙌"]))

    elif "چی کار می‌کنی" in text or "چیکار میکنی" in text:
        await bot_reply(message, random.choice(["هیچی، منتظر پیامتم 😄", "دارم تو گروه می‌چرخم 😎"]))

    elif "بیداری" in text:
        await bot_reply(message, random.choice(["آره بیدارم 😄", "همیشه بیدارم، ربات که نمی‌خوابه 😄"]))

    elif "خوابیدی" in text:
        await bot_reply(message, random.choice(["نه، ربات‌ها نمی‌خوابن 😄", "نه بابا، ۲۴ ساعته آنلاینم 🤖"]))

    elif "حوصله ندارم" in text:
        await bot_reply(message, random.choice(["یکم استراحت کن، درست میشه 🙂", "بیخیال، بازی کنیم حالت بهتر شه؟ 🎮"]))

    elif "ناراحتم" in text:
        await bot_reply(message, random.choice(["امیدوارم زودتر بهتر بشه 🌸", "درست میشه، نگران نباش 🙂"]))

    elif "خوشحالم" in text:
        await bot_reply(message, random.choice(["خوشحالی تو هم خوشحالم می‌کنه 😄", "عالیه! همینطور شاد بمون 🎉"]))

    elif "عالیه" in text or "خوبه" in text:
        await bot_reply(message, random.choice(["👍", "😄👌"]))

    elif "بد شد" in text:
        await bot_reply(message, random.choice(["😕", "اوه، امیدوارم درست بشه 🙏"]))

    elif text == "وای":
        await bot_reply(message, random.choice(["چی شد؟ 😅", "هول نکن، بگو چی شده 😄"]))

    elif "جدی؟" in text or "راست میگی؟" in text:
        await bot_reply(message, random.choice(["آره جدی میگم 😄", "صد در صد راست میگم 😎"]))

    elif text == "چرا؟":
        await bot_reply(message, random.choice(["دلیل خاصی نداشت 😅", "همینجوری گفتم 😄"]))

    elif "یعنی چی؟" in text:
        await bot_reply(message, random.choice(["یعنی همون که گفتم 😄", "خودتم می‌دونی یعنی چی 😉"]))

    elif text == "آره":
        await bot_reply(message, random.choice(["باشه 👍", "خوبه پس 😄"]))

    elif text == "نه":
        await bot_reply(message, random.choice(["باشه، هرجور راحتی 🙂", "اوکی، مشکلی نیست 👍"]))

    elif text in ("باشه", "اوکی", "قبول"):
        await bot_reply(message, random.choice(["👌", "عالیه 😄"]))

    elif "نمی‌دونم" in text or "نمیدونم" in text or "یادم نیست" in text:
        await bot_reply(message, random.choice(["مشکلی نیست 🙂", "عیبی نداره، بعداً یادت میاد 😄"]))

    elif "کی هستی" in text:
        await bot_reply(message, random.choice(["من پرسیا هستم، یه ربات کمکی 🤖", "من پرسیام، اینجام کمکت کنم 😄"]))

    elif "رباتی؟" in text:
        await bot_reply(message, random.choice(["آره، ربات‌ام 🤖", "دقیقاً، یه ربات باحالم 😎"]))

    elif "آدمی؟" in text:
        await bot_reply(message, random.choice(["نه، ربات‌ام 😄", "نه بابا، از جنس کد و الگوریتمم 🤖"]))

    elif "دوستت دارم" in text:
        await bot_reply(message, random.choice(["منم دوستت دارم داداش ❤️", "خیلی مهربونی، منم بهت حس خوبی دارم 🙌"]))

    elif "دلم گرفته" in text:
        await bot_reply(message, random.choice(["امیدوارم زودتر بهتر بشه 🌸", "پیشم درد و دل کن، سبک میشی 🙂"]))

    elif text == "تنهام":
        await bot_reply(message, random.choice(["من اینجام، تنها نیستی 🙂", "هروقت خواستی حرف بزنی من هستم ❤️"]))

    elif text_raw.startswith("همگانی"):
        if not is_bot_admin(uid):
            await bot_reply(message, "⛔ این دستور فقط برای سازنده ربات‌ه.")
        else:
            broadcast_text = text_raw.replace("همگانی", "", 1).strip()
            if not broadcast_text:
                await bot_reply(message, "بنویس: «همگانی [متن پیام]»")
            else:
                sent, failed = 0, 0
                for target_uid, target_data in list(users.items()):
                    target_chat_id = target_data.get("pv_chat_id")
                    if not target_chat_id:
                        failed += 1
                        continue
                    try:
                        await maybe_await(bot.send_message(target_chat_id, broadcast_text))
                        sent += 1
                    except Exception as e:
                        failed += 1
                        print("خطا در ارسال به", target_chat_id, ":", e)
                await bot_reply(message, f"✅ پیام همگانی ارسال شد.\nموفق: {sent} | ناموفق: {failed}")

    elif "قابلیت" in text or "کمک" in text:
        await bot_reply(message, f"""🫡 در خدمتتم! این‌جا لیست کامل قابلیت‌های منه 👇

╔══════✦ 🤖 قابلیت‌های ربات {BOT_BRAND} ✦══════╗

💬 عمومی
سلام / خوبی / صبح بخیر / شب بخیر / جوک / شانس / فال / تاس
📅 تاریخ (شمسی + میلادی)  |  🕒 ساعت
🎯 چالش  |  🎯 انتخاب کن [گزینه۱] یا [گزینه۲]

🧮 ماشین‌حساب و ارز
فقط بنویس مثلا: «5 + 3»، «10 - 2»، «4 ضرب در 6»، «20 تقسیم بر 4»
تبدیل ارز: بنویس مثلا «1000 دلار به تومان» یا «50 یورو به تومان»
ارزهای پشتیبانی‌شده: دلار، یورو، یوان، پوند، درهم، لیر

👤 پروفایل و آمار
👤 پروفایل  |  📊 آمار  |  👥 کاربران
📛 تنظیم اسم [نام]  |  😀 تنظیم ایموجی [شکلک]
🏷 تنظیم لقب [متن]  |  🌍 تنظیم اصل [متن]
🥇 رتبه (جدول برترین‌ها)

💰 اقتصاد
🎁 جایزه روزانه (با استریک)  |  🎰 گردونه شانس
🪙 شرط [مقدار سکه]  |  🏪 فروشگاه  |  خرید [آیتم]
🐉 شکار (جمع کردن موجودات)

🎮 بازی‌ها (کاملا متنی، فقط با فرستادن عدد/متن بازی می‌کنی)
🎮 حدس عدد  |  ❌⭕ دوز  |  🧩 معما  |  📝 مسابقه
⚽ پنالتی (+ 🏟 فروشگاه پنالتی)
🚔 فرار از زندان (داستان شاخه‌ای با چند سرنوشت متفاوت)
🎭 جرعت حقیقت  |  🕵️ دروغ سنج (بازی کوتاه و خنده‌دار)
🎲 شروع قرعه کشی  |  شرکت  |  برنده قرعه کشی

🛡️ مدیریت و امنیت گروه
فعال (ثبت گروه و مالک)  |  لیست قفل ها
قفل لینک / باز کردن قفل لینک
قفل اسپم / باز کردن قفل اسپم
قفل منشن زیاد / باز کردن قفل منشن زیاد
قفل فوروارد / باز کردن قفل فوروارد
قفل الفاظ نامناسب / باز کردن قفل الفاظ نامناسب

(اگه اسممو صدا بزنی «پرسیا» هم جواب می‌دم 😄)
╚═══════════════════════════════════╝""")

    else:
        pass


# ---------------------------------------------------------------------------
# سرور کوچیک keep-alive - فقط برای هاستینگ‌های رایگانی مثل Render لازمه که
# انتظار دارن یه وب‌سرور روی یه پورت گوش بده. اگه رو سرور اختصاصی/VPS خودت
# اجرا می‌کنی که نیازی به این نیست و خودش غیرفعال می‌مونه.
# ---------------------------------------------------------------------------
def start_keep_alive_server():
    port_env = os.environ.get("PORT")
    if not port_env:
        return
    try:
        port = int(port_env)
    except ValueError:
        return

    class PingHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK - PersiaBot is alive")

        def log_message(self, format, *args):
            pass  # لاگ‌های اضافه‌ی هر پینگ رو خاموش می‌کنیم

    try:
        server = HTTPServer(("0.0.0.0", port), PingHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        print(f"✅ سرور کوچیک keep-alive روی پورت {port} بالا اومد (برای Render/هاستینگ‌های مشابه)")
    except Exception as e:
        print("خطا در راه‌اندازی سرور keep-alive:", e)


start_keep_alive_server()
load_data()
bot.run()
