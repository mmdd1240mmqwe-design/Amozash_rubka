"""
SHADOW CASE — procedural content pools and case generator.

Every call to generate_new_case() produces a fully different mystery:
different victim, different suspects/personalities/alibis, different
locations, different murder weapon and motive, and a different culprit.
"""

import random

VICTIM_NAMES = [
    "آرمان کیانی", "سارا حسینی", "بهنام رادفر", "نگار صالحی", "کیوان مرادی",
    "لیلا اکبری", "فرهاد نجفی", "مریم توکلی", "رضا شریفی", "الناز رستمی",
    "امیرحسین قاسمی", "شیدا فروزان", "دانیال عزیزی", "ترانه یوسفی", "پویا احمدی",
]

SUSPECT_NAME_POOL = [
    "حسین دلاور", "مهتاب صدر", "کامران ایزدی", "رویا نیک‌فر", "بابک سلطانی",
    "ندا کیانپور", "فرید امینی", "گلناز رحیمی", "سامان بختیاری", "پریسا جوادی",
    "آرش تهرانی", "مینا شکوری", "یاشار پارسا", "الهام موسوی", "سهیل کریمی",
    "ژاله عابدی", "نیما فرهادی", "رعنا حیدری", "امید صفایی", "بیتا نظری",
]

PERSONALITIES = [
    {"name": "عصبی و بی‌قرار", "tell_bonus": 15},
    {"name": "آرام و کنترل‌شده", "tell_bonus": -10},
    {"name": "دروغگوی حرفه‌ای", "tell_bonus": -20},
    {"name": "صادق ولی ترسو", "tell_bonus": 10},
    {"name": "پرخاشگر و تهاجمی", "tell_bonus": 5},
    {"name": "سرد و بی‌تفاوت", "tell_bonus": -5},
    {"name": "مرموز و کم‌حرف", "tell_bonus": 0},
]

ALIBIS = [
    "میگه اون شب خونه بوده و تنها فیلم می‌دیده.",
    "ادعا می‌کنه سرکار بوده تا دیر وقت.",
    "میگه با یه دوست قدیمی تو کافه بوده ولی اسمشو دقیق یادش نیست.",
    "میگه تو جاده بوده و ماشینش خراب شده.",
    "ادعا می‌کنه خواب بوده و گوشیشم خاموش بوده.",
    "میگه داشته تو پارک قدم می‌زده که ذهنش آروم بشه.",
    "ادعا می‌کنه مهمونی خانوادگی بوده و همه دیدنش.",
    "میگه رفته بوده بیرون شهر و شب برنگشته.",
    "میگه تنها تو اتاقش نشسته بوده و به کسی زنگ نزده.",
    "ادعا می‌کنه داشته کتاب می‌خونده و متوجه زمان نشده.",
]

VICTIM_QUESTIONS_ANSWERS = [
    "میگه {victim} آدم آرومی بود و دشمن خاصی نداشت... حداقل که خودش خبر داشته باشه.",
    "میگه چند وقت اخیر با {victim} بحثش شده بود ولی چیز مهمی نبوده.",
    "میگه آخرین بار {victim} رو تو یه مهمونی دیده، حالش خوب بود.",
    "میگه از وقتی {victim} گم شده، هیچکس درست حرف نمی‌زنه.",
    "میگه شنیده {victim} یه مدت نگران یه چیزی بوده ولی نگفته چی.",
]

WEAPONS = [
    "چاقوی شکاری", "طناب دار", "سلاح گرم قدیمی",
    "سم نامشخص", "جسم سنگین و تیز", "خفگی با دست",
]

MOTIVES = [
    "انتقام یه بدهی قدیمی", "پول و ارث", "یه رابطه‌ی پنهونی",
    "ترس از افشا شدن یه راز", "حسادت شغلی", "دعوای خانوادگی قدیمی",
]

LOCATION_NAME_POOL = [
    "خونه قربانی", "بار متروکه محله", "انبار کنار راه‌آهن", "پارک شهر",
    "اداره پلیس منطقه", "کافه گوشه خیابون", "ایستگاه قدیمی قطار",
    "هتل ارزون‌قیمت", "آپارتمان یکی از مظنونین", "گاراژ متروکه",
    "کنار رودخونه", "کتابخونه عمومی شهر",
]

JUNK_ITEMS = [
    {"name": "روزنامه کهنه", "desc": "یه روزنامه‌ی چند روز پیش، خبر خاصی نداره."},
    {"name": "فندک شکسته", "desc": "یه فندک زنگ‌زده که دیگه روشن نمیشه."},
    {"name": "ساندویچ سرد", "desc": "یه ساندویچ نصفه که هنوز خوردنیه.",
     "consumable": "hunger", "amount": 30},
    {"name": "بطری آب معدنی", "desc": "نیمه پره، هنوز سالمه.",
     "consumable": "thirst", "amount": 30},
    {"name": "دکمه پیراهن", "desc": "یه دکمه‌ی معمولی، به نظر ربطی به پرونده نداره."},
    {"name": "بلیط اتوبوس باطل‌شده", "desc": "مال چند هفته پیشه."},
    {"name": "کیف پول خالی", "desc": "هیچ کارتی توش نیست."},
    {"name": "قوطی نوشابه له‌شده", "desc": "کسی همینجا نشسته بوده."},
    {"name": "دفترچه خط‌خطی", "desc": "چندتا شماره تلفن ناخونا توش نوشته شده."},
    {"name": "ساعت مچی خراب", "desc": "عقربه‌هاش رو ساعت حادثه وایساده... جالبه ولی معلوم نیست مال کیه."},
    {"name": "نان خشک‌شده", "desc": "دیگه خوردنی نیست.", "consumable": "hunger", "amount": 10},
    {"name": "بطری آبجو خالی", "desc": "بوی الکل هنوز میاد."},
    {"name": "سیب گاززده", "desc": "یکی همینجا داشته غذا می‌خورده.", "consumable": "hunger", "amount": 15},
    {"name": "قمقمه نیمه‌پر", "desc": "آب داخلش هنوز تمیزه.", "consumable": "thirst", "amount": 20},
]

RADIO_PARTS = ["باتری رادیو", "آنتن شکسته", "سیم رابط مسی"]

# --------------------------------------------------------------------------- #


def generate_new_case() -> dict:
    victim_name = random.choice(VICTIM_NAMES)

    suspect_names = random.sample(SUSPECT_NAME_POOL, k=4)
    culprit_index = random.randrange(4)
    weapon = random.choice(WEAPONS)
    motive = random.choice(MOTIVES)

    suspects = []
    for i, name in enumerate(suspect_names):
        personality = random.choice(PERSONALITIES)
        suspects.append({
            "name": name,
            "personality": personality["name"],
            "tell_bonus": personality["tell_bonus"],
            "alibi": random.choice(ALIBIS),
            "victim_line": random.choice(VICTIM_QUESTIONS_ANSWERS).format(victim=victim_name),
            "is_culprit": (i == culprit_index),
        })

    culprit_name = suspects[culprit_index]["name"]

    location_names = random.sample(LOCATION_NAME_POOL, k=4)
    locked_index = random.randrange(4)
    locations = []
    for i, name in enumerate(location_names):
        locked = (i == locked_index)
        code = [random.randint(1, 6) for _ in range(3)] if locked else None
        locations.append({"name": name, "locked": locked, "code": code})

    # ---- key clue items, spread across three different locations -------- #
    key_slots = random.sample(range(4), k=3)

    weapon_item = {
        "name": f"ردی از {weapon}",
        "desc": f"وقتی از نزدیک نگاه می‌کنی، رد واضحی از {weapon} روی صحنه به چشم می‌خوره. "
                f"انگار قاتل عجله داشته و اثری از خودش جا گذاشته.",
        "is_key_clue": True,
        "location_index": key_slots[0],
    }
    motive_item = {
        "name": "سرنخ انگیزه",
        "desc": f"یه یادداشت نیمه‌سوخته که به‌وضوح به «{motive}» اشاره داره. "
                f"انگار یکی دلیل محکمی برای این کار داشته.",
        "is_key_clue": True,
        "location_index": key_slots[1],
    }
    culprit_item = {
        "name": "ردپای شخصی",
        "desc": f"این سرنخ به‌وضوح به {culprit_name} اشاره داره — انگار خودش این‌جا ردی از خودش جا گذاشته.",
        "is_key_clue": True,
        "location_index": key_slots[2],
    }

    key_items = [weapon_item, motive_item, culprit_item]

    # ---- junk / flavor / consumable items, a few per location ------------ #
    junk_items = []
    junk_pool = random.sample(JUNK_ITEMS, k=min(8, len(JUNK_ITEMS)))
    for idx, junk in enumerate(junk_pool):
        junk_items.append({
            "name": junk["name"],
            "desc": junk["desc"],
            "is_key_clue": False,
            "location_index": idx % 4,
            "consumable": junk.get("consumable"),
            "amount": junk.get("amount", 0),
        })

    # ---- optional side-quest: radio repair (assembly mini-game) ---------- #
    radio_owner_index = random.randrange(4)
    assembly_order = RADIO_PARTS[:]
    random.shuffle(assembly_order)
    assembly_items = []
    for i, part_name in enumerate(RADIO_PARTS):
        assembly_items.append({
            "name": part_name,
            "desc": "یه قطعه‌ی قدیمی رادیو. شاید بشه باهاش یه رادیوی خراب رو تعمیر کرد.",
            "is_key_clue": False,
            "location_index": (locked_index + i + 1) % 4,
            "assembly_step": i + 1,
        })

    all_items = key_items + junk_items + assembly_items

    combo_result = (
        f"با کنار هم گذاشتن ردِ {weapon} و سرنخ مربوط به {culprit_name}، "
        f"تقریباً مطمئن می‌شی که قاتل خودشه."
    )

    return {
        "victim_name": victim_name,
        "weapon": weapon,
        "motive": motive,
        "culprit_name": culprit_name,
        "suspects": suspects,
        "locations": locations,
        "items": all_items,
        "combo_a_name": weapon_item["name"],
        "combo_b_name": culprit_item["name"],
        "combo_result": combo_result,
        "radio_owner_index": radio_owner_index,
        "assembly_order": assembly_order,
    }
