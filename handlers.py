"""
SHADOW CASE — all Telegram handlers.
"""

import random

from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import config
import db
import gamedata
import keyboards as kb
import minigames

router = Router()


# --------------------------------------------------------------------------- #
# FSM STATES
# --------------------------------------------------------------------------- #

class LockpickState(StatesGroup):
    guessing = State()


class DeduceState(StatesGroup):
    choosing_weapon = State()
    choosing_motive = State()


class AssemblyState(StatesGroup):
    picking = State()


# --------------------------------------------------------------------------- #
# HELPERS
# --------------------------------------------------------------------------- #

def bar(value: int, maximum: int = 100, length: int = 10) -> str:
    value = max(0, min(maximum, value))
    filled = round(length * value / maximum) if maximum else 0
    return "▰" * filled + "▱" * (length - filled)


async def status_text(case) -> str:
    return (
        f"🕵️ <b>پرونده‌ی «{case['victim_name']}»</b>\n"
        f"روز {case['day']} از {case['max_days']}\n\n"
        f"❤️ سلامتی: {bar(case['health'])} {case['health']}\n"
        f"🔋 استقامت: {bar(case['stamina'])} {case['stamina']}\n"
        f"🍗 گرسنگی: {bar(case['hunger'])} {case['hunger']}\n"
        f"💧 تشنگی: {bar(case['thirst'])} {case['thirst']}\n"
        f"🌟 اعتبار: {bar(case['reputation'])} {case['reputation']}\n"
    )


NO_CASE_TEXT = "هنوز پرونده‌ی فعالی نداری. برای شروع دستور /start رو بزن."


async def send_no_case(event):
    if isinstance(event, CallbackQuery):
        await event.answer(NO_CASE_TEXT, show_alert=True)
    else:
        await event.answer(NO_CASE_TEXT)


async def check_case_alive(case, message_to_edit=None) -> bool:
    """If the case just expired (deadline or death), close it out and notify. Returns False if not alive."""
    if case["status"] != "active":
        return case["status"] == "active"

    if case["day"] > case["max_days"]:
        await db.update_case(case["id"], status="failed")
        await db.add_log(case["id"], case["day"], "⏳ زمان تموم شد. پرونده سرد شد و برای همیشه بسته موند.")
        text = (
            "⏳ <b>پرونده سرد شد</b>\n\n"
            f"زمان تموم شد و هیچ‌وقت نفهمیدی چه بلایی سر {case['victim_name']} اومد. "
            "پرونده برای همیشه تو بایگانی خاک می‌خوره.\n\n"
            "برای شروع یه پرونده‌ی جدید /newcase رو بزن."
        )
        if message_to_edit:
            await message_to_edit.answer(text)
        return False

    if case["health"] <= 0:
        await db.update_case(case["id"], status="failed")
        await db.add_log(case["id"], case["day"], "🚑 از پا افتادی و بیهوش شدی. پرونده ناتمام موند.")
        text = (
            "🚑 <b>از پا افتادی</b>\n\n"
            "بدنت دیگه تحمل نداشت. گرسنگی و تشنگی کارت رو ساختن و بیهوش شدی. "
            "پرونده ناتمام موند.\n\n"
            "برای شروع یه پرونده‌ی جدید /newcase رو بزن."
        )
        if message_to_edit:
            await message_to_edit.answer(text)
        return False

    return True


async def advance_turn(case):
    new_turn = case["turn"] + 1
    new_day = case["day"] + (1 if new_turn % config.TURNS_PER_DAY == 0 else 0)
    await db.update_case(case["id"], turn=new_turn, day=new_day)


async def spend_search(case):
    new_stamina = max(0, case["stamina"] - config.SEARCH_STAMINA_COST)
    new_hunger = max(0, case["hunger"] - config.SEARCH_HUNGER_COST)
    new_thirst = max(0, case["thirst"] - config.SEARCH_THIRST_COST)
    loss = config.STARVATION_HEALTH_LOSS if (new_hunger == 0 or new_thirst == 0) else 0
    new_health = max(0, case["health"] - loss)
    await db.update_case(case["id"], stamina=new_stamina, hunger=new_hunger,
                          thirst=new_thirst, health=new_health)
    await advance_turn(case)


async def spend_talk(case):
    new_stamina = max(0, case["stamina"] - config.TALK_STAMINA_COST)
    new_hunger = max(0, case["hunger"] - config.TALK_HUNGER_COST)
    new_thirst = max(0, case["thirst"] - config.TALK_THIRST_COST)
    loss = config.STARVATION_HEALTH_LOSS if (new_hunger == 0 or new_thirst == 0) else 0
    new_health = max(0, case["health"] - loss)
    await db.update_case(case["id"], stamina=new_stamina, hunger=new_hunger,
                          thirst=new_thirst, health=new_health)
    await advance_turn(case)


# --------------------------------------------------------------------------- #
# START / MAIN MENU
# --------------------------------------------------------------------------- #

@router.message(CommandStart())
async def cmd_start(message: Message):
    await db.ensure_user(message.from_user.id, message.from_user.first_name)
    case = await db.get_active_case(message.from_user.id)

    if case is None:
        case_id = await db.create_case(message.from_user.id)
        case = await db.get_case(case_id)
        intro = (
            "🌆 <b>SHADOW CASE</b>\n\n"
            f"«{case['victim_name']}» چند روزه که ناپدید شده. خانواده‌اش دیگه امیدی ندارن، "
            "پلیس هم پرونده رو بایگانی کرده... ولی تو نه.\n\n"
            "چهار نفر مظنون هستن، یه سلاح، یه انگیزه — و فقط چند روز وقت داری قبل از اینکه "
            "پرونده برای همیشه سرد بشه.\n\n"
        )
        await message.answer(intro + await status_text(case), reply_markup=kb.main_menu_kb())
        return

    await message.answer("ادامه‌ی پرونده‌ی فعلی:\n\n" + await status_text(case), reply_markup=kb.main_menu_kb())


@router.message(Command("newcase"))
async def cmd_newcase(message: Message):
    case = await db.get_active_case(message.from_user.id)
    if case is None:
        case_id = await db.create_case(message.from_user.id)
        case = await db.get_case(case_id)
        await message.answer(
            f"🌆 پرونده‌ی جدید: ناپدید شدن «{case['victim_name']}»\n\n" + await status_text(case),
            reply_markup=kb.main_menu_kb(),
        )
        return

    await message.answer(
        "⚠️ یه پرونده‌ی فعال داری. اگه پرونده‌ی جدید شروع کنی، پرونده‌ی فعلی برای همیشه ناتمام می‌مونه.\n"
        "مطمئنی؟",
        reply_markup=kb.newcase_confirm_kb(),
    )


@router.callback_query(F.data == "newcase_confirm")
async def cb_newcase_confirm(call: CallbackQuery):
    old = await db.get_active_case(call.from_user.id)
    if old:
        await db.update_case(old["id"], status="abandoned")
        await db.add_log(old["id"], old["day"], "🗂️ کارآگاه این پرونده رو رها کرد و رفت سراغ یه پرونده‌ی دیگه.")

    case_id = await db.create_case(call.from_user.id)
    case = await db.get_case(case_id)
    await call.message.edit_text(
        f"🌆 پرونده‌ی جدید: ناپدید شدن «{case['victim_name']}»\n\n" + await status_text(case),
        reply_markup=kb.main_menu_kb(),
    )
    await call.answer()


@router.callback_query(F.data == "back_main")
@router.callback_query(F.data == "m_status")
async def cb_main_menu(call: CallbackQuery):
    case = await db.get_active_case(call.from_user.id)
    if case is None:
        await send_no_case(call)
        return
    if not await check_case_alive(case, call.message):
        await call.answer()
        return
    await call.message.edit_text(await status_text(case), reply_markup=kb.main_menu_kb())
    await call.answer()


@router.message(Command("status"))
async def cmd_status(message: Message):
    case = await db.get_active_case(message.from_user.id)
    if case is None:
        await send_no_case(message)
        return
    if not await check_case_alive(case, message):
        return
    await message.answer(await status_text(case), reply_markup=kb.main_menu_kb())


# --------------------------------------------------------------------------- #
# REST
# --------------------------------------------------------------------------- #

@router.callback_query(F.data == "m_rest")
async def cb_rest(call: CallbackQuery):
    case = await db.get_active_case(call.from_user.id)
    if case is None:
        await send_no_case(call)
        return
    if not await check_case_alive(case, call.message):
        await call.answer()
        return

    new_stamina = min(100, case["stamina"] + config.REST_STAMINA_GAIN)
    new_hunger = min(100, case["hunger"] + config.REST_HUNGER_GAIN)
    new_thirst = min(100, case["thirst"] + config.REST_THIRST_GAIN)
    new_day = case["day"] + 1
    await db.update_case(case["id"], stamina=new_stamina, hunger=new_hunger,
                          thirst=new_thirst, day=new_day)
    await db.add_log(case["id"], new_day, "😴 چند ساعتی استراحت کردی و دوباره جون گرفتی.")

    case = await db.get_case(case["id"])
    if not await check_case_alive(case, call.message):
        await call.answer()
        return

    await call.answer("استراحت کردی!")
    await call.message.edit_text(await status_text(case), reply_markup=kb.main_menu_kb())


# --------------------------------------------------------------------------- #
# EXPLORE / SEARCH / LOCKPICK
# --------------------------------------------------------------------------- #

@router.callback_query(F.data == "m_explore")
async def cb_explore_menu(call: CallbackQuery):
    case = await db.get_active_case(call.from_user.id)
    if case is None:
        await send_no_case(call)
        return
    if not await check_case_alive(case, call.message):
        await call.answer()
        return

    locations = await db.get_locations(case["id"])
    await call.message.edit_text(
        "🔍 <b>کاوش مکان‌ها</b>\nیه مکان رو انتخاب کن:",
        reply_markup=kb.locations_kb(locations),
    )
    await call.answer()


@router.callback_query(F.data.startswith("loc_"))
async def cb_location_detail(call: CallbackQuery):
    location_id = int(call.data.removeprefix("loc_"))
    location = await db.get_location(location_id)
    if not location:
        await call.answer("این مکان دیگه در دسترس نیست.", show_alert=True)
        return

    lock_state = "🔒 قفله" if (location["locked"] and not location["unlocked"]) else "🔓 باز است"
    await call.message.edit_text(
        f"📍 <b>{location['name']}</b>\nوضعیت: {lock_state}",
        reply_markup=kb.location_detail_kb(location),
    )
    await call.answer()


@router.callback_query(F.data.startswith("search_"))
async def cb_search_location(call: CallbackQuery):
    location_id = int(call.data.removeprefix("search_"))
    case = await db.get_active_case(call.from_user.id)
    if case is None:
        await send_no_case(call)
        return
    if not await check_case_alive(case, call.message):
        await call.answer()
        return
    if case["stamina"] <= 0:
        await call.answer("دیگه توان نداری، باید استراحت کنی. 😮‍💨", show_alert=True)
        return

    location = await db.get_location(location_id)
    unfound = await db.get_unfound_items(case["id"], location_id)

    if not unfound:
        result_text = "این مکان رو قبلاً به‌طور کامل گشتی. چیز جدیدی نیست."
    elif random.random() < 0.75:
        item = random.choice(unfound)
        await db.update_item(item["id"], found=1, in_inventory=1)
        tag = "🧩 سرنخ کلیدی" if item["is_key_clue"] else "📦 وسیله"
        result_text = f"پیدا کردی: {tag} «{item['name']}»\n{item['description']}"
        await db.add_log(case["id"], case["day"], f"در {location['name']} پیدا کردی: {item['name']}")
    else:
        result_text = "این بار تو جستجو چیزی گیرت نیومد. شاید بار بعد بهتر بگردی."

    await spend_search(case)
    case = await db.get_case(case["id"])
    if not await check_case_alive(case, call.message):
        await call.answer()
        return

    await call.answer(result_text, show_alert=True)
    await call.message.edit_text(
        f"📍 <b>{location['name']}</b>\nوضعیت: 🔓 باز است\n\n{await status_text(case)}",
        reply_markup=kb.location_detail_kb(location),
    )


@router.callback_query(F.data.startswith("lockpick_"))
async def cb_lockpick_start(call: CallbackQuery, state: FSMContext):
    location_id = int(call.data.removeprefix("lockpick_"))
    location = await db.get_location(location_id)
    if not location or not location["locked"] or location["unlocked"]:
        await call.answer("قفلی برای باز کردن نیست.", show_alert=True)
        return

    await state.set_state(LockpickState.guessing)
    await state.update_data(location_id=location_id, digits=[])
    await call.message.edit_text(
        "🔓 <b>باز کردن قفل</b>\n\n"
        "یه قفل عددی سه‌رقمیه (هر رقم بین ۱ تا ۶). سه رقم رو به ترتیب انتخاب کن.\n"
        "بعد از هر حدس بهت می‌گم چندتا رقم دقیقاً درستن و چندتا فقط تو کد هستن ولی جای اشتباه.\n\n"
        "رقم اول رو انتخاب کن:",
        reply_markup=kb.digit_kb(),
    )
    await call.answer()


@router.callback_query(LockpickState.guessing, F.data.startswith("dig_"))
async def cb_lockpick_digit(call: CallbackQuery, state: FSMContext):
    digit = int(call.data.removeprefix("dig_"))
    data = await state.get_data()
    digits = data["digits"] + [digit]
    location_id = data["location_id"]

    if len(digits) < 3:
        await state.update_data(digits=digits)
        await call.message.edit_text(
            f"رقم‌های انتخاب‌شده: {' '.join(str(d) for d in digits)}\nرقم بعدی رو انتخاب کن:",
            reply_markup=kb.digit_kb(),
        )
        await call.answer()
        return

    # third digit entered -> evaluate
    location = await db.get_location(location_id)
    case = await db.get_active_case(call.from_user.id)
    code = minigames.parse_code(location["lock_code"])
    exact, partial = minigames.lockpick_feedback(code, digits)

    if exact == 3:
        await db.update_location(location_id, unlocked=1)
        await db.add_log(case["id"], case["day"], f"🔓 قفل «{location['name']}» رو باز کردی.")
        await state.clear()
        await call.answer("قفل باز شد! 🎉", show_alert=True)
        location = await db.get_location(location_id)
        await call.message.edit_text(
            f"📍 <b>{location['name']}</b>\nوضعیت: 🔓 باز است",
            reply_markup=kb.location_detail_kb(location),
        )
        return

    new_stamina = max(0, case["stamina"] - config.LOCKPICK_FAIL_STAMINA_COST)
    await db.update_case(case["id"], stamina=new_stamina)

    await state.update_data(digits=[])
    await call.answer(
        f"❌ باز نشد.\nدقیق درست: {exact} | تو کد هست ولی جای غلط: {partial}\n(۵ استقامت مصرف شد)",
        show_alert=True,
    )
    if new_stamina <= 0:
        await state.clear()
        case = await db.get_case(case["id"])
        await check_case_alive(case, call.message)
        return

    await call.message.edit_text(
        "🔓 دوباره امتحان کن. رقم اول رو انتخاب کن:",
        reply_markup=kb.digit_kb(),
    )


# --------------------------------------------------------------------------- #
# SUSPECTS / DIALOGUE
# --------------------------------------------------------------------------- #

@router.callback_query(F.data == "m_suspects")
async def cb_suspects_menu(call: CallbackQuery):
    case = await db.get_active_case(call.from_user.id)
    if case is None:
        await send_no_case(call)
        return
    if not await check_case_alive(case, call.message):
        await call.answer()
        return

    suspects = await db.get_suspects(case["id"])
    await call.message.edit_text(
        "🕵️ <b>مظنونین</b>\nیکی رو انتخاب کن تا بازجویی کنی:",
        reply_markup=kb.suspects_kb(suspects),
    )
    await call.answer()


async def _suspect_detail_view(call: CallbackQuery, suspect):
    text = (
        f"🧑 <b>{suspect['name']}</b>\n"
        f"شخصیت: {suspect['personality']}\n"
        f"اعتماد به تو: {bar(suspect['trust'])} {suspect['trust']}\n"
        f"سطح شک بهش: {bar(suspect['suspicion'])} {suspect['suspicion']}\n"
    )
    await call.message.edit_text(text, reply_markup=kb.suspect_detail_kb(suspect))


@router.callback_query(F.data.startswith("sus_"))
async def cb_suspect_detail(call: CallbackQuery):
    suspect_id = int(call.data.removeprefix("sus_"))
    suspect = await db.get_suspect(suspect_id)
    if not suspect:
        await call.answer("این مظنون دیگه در دسترس نیست.", show_alert=True)
        return
    await _suspect_detail_view(call, suspect)
    await call.answer()


@router.callback_query(F.data.startswith("ask_victim_"))
async def cb_ask_victim(call: CallbackQuery):
    suspect_id = int(call.data.removeprefix("ask_victim_"))
    case = await db.get_active_case(call.from_user.id)
    if case is None:
        await send_no_case(call)
        return
    if not await check_case_alive(case, call.message):
        await call.answer()
        return

    suspect = await db.get_suspect(suspect_id)
    new_trust = min(100, suspect["trust"] + 3)
    await db.update_suspect(suspect_id, trust=new_trust, interviewed=1)
    await spend_talk(case)

    case = await db.get_case(case["id"])
    if not await check_case_alive(case, call.message):
        await call.answer()
        return

    await call.answer(suspect["victim_line"], show_alert=True)
    suspect = await db.get_suspect(suspect_id)
    await _suspect_detail_view(call, suspect)


@router.callback_query(F.data.startswith("ask_alibi_"))
async def cb_ask_alibi(call: CallbackQuery):
    suspect_id = int(call.data.removeprefix("ask_alibi_"))
    case = await db.get_active_case(call.from_user.id)
    if case is None:
        await send_no_case(call)
        return
    if not await check_case_alive(case, call.message):
        await call.answer()
        return

    suspect = await db.get_suspect(suspect_id)
    text = suspect["alibi"]
    new_suspicion = suspect["suspicion"]

    if suspect["is_culprit"]:
        base_chance = 0.30 + (suspect["tell_bonus"] / 100)
        if random.random() < max(0.05, base_chance):
            text += "\n\n🤔 یه لحظه مکث کرد قبل از جواب دادن... چیزی این وسط جور در نمیاد."
            new_suspicion = min(100, suspect["suspicion"] + 15)

    await db.update_suspect(suspect_id, suspicion=new_suspicion, interviewed=1)
    await spend_talk(case)

    case = await db.get_case(case["id"])
    if not await check_case_alive(case, call.message):
        await call.answer()
        return

    await call.answer(text, show_alert=True)
    suspect = await db.get_suspect(suspect_id)
    await _suspect_detail_view(call, suspect)


@router.callback_query(F.data.startswith("present_"))
async def cb_present_menu(call: CallbackQuery):
    suspect_id = int(call.data.removeprefix("present_"))
    case = await db.get_active_case(call.from_user.id)
    if case is None:
        await send_no_case(call)
        return
    if not await check_case_alive(case, call.message):
        await call.answer()
        return

    inventory = await db.get_inventory(case["id"])
    key_items = [it for it in inventory if it["is_key_clue"]]
    if not key_items:
        await call.answer("هنوز مدرک کلیدی‌ای برای نشون دادن نداری.", show_alert=True)
        return

    await call.message.edit_text(
        "📤 کدوم مدرک رو نشون بدم؟",
        reply_markup=kb.present_items_kb(key_items, suspect_id),
    )
    await call.answer()


@router.callback_query(F.data.startswith("pres_"))
async def cb_present_item(call: CallbackQuery):
    _, suspect_id, item_id = call.data.split("_")
    suspect_id, item_id = int(suspect_id), int(item_id)

    case = await db.get_active_case(call.from_user.id)
    if case is None:
        await send_no_case(call)
        return
    if not await check_case_alive(case, call.message):
        await call.answer()
        return

    suspect = await db.get_suspect(suspect_id)
    item = await db.get_item(item_id)

    culprit_link_item = (item["name"] == "ردپای شخصی")

    if suspect["is_culprit"] and culprit_link_item:
        new_trust = max(0, suspect["trust"] - 15)
        new_suspicion = min(100, suspect["suspicion"] + 35)
        text = "😳 رنگش پرید. سعی کرد خونسرد باشه ولی دستاش می‌لرزید. این یعنی یه چیزی رو داره پنهون می‌کنه."
    elif suspect["is_culprit"]:
        new_trust = max(0, suspect["trust"] - 5)
        new_suspicion = min(100, suspect["suspicion"] + 10)
        text = "با آرامش نگاه کرد و گفت این ربطی به اون نداره... ولی یه لحظه چشماش رو ازت دزدید."
    else:
        new_trust = min(100, suspect["trust"] + 5)
        new_suspicion = suspect["suspicion"]
        text = "با تعجب نگاه کرد و گفت اصلاً نمی‌دونه این چیه. به نظر واقعی میاد."

    await db.update_suspect(suspect_id, trust=new_trust, suspicion=new_suspicion)
    await spend_talk(case)

    case = await db.get_case(case["id"])
    if not await check_case_alive(case, call.message):
        await call.answer()
        return

    await call.answer(text, show_alert=True)
    suspect = await db.get_suspect(suspect_id)
    await _suspect_detail_view(call, suspect)


# --------------------------------------------------------------------------- #
# INVENTORY / COMBINE / CONSUME
# --------------------------------------------------------------------------- #

@router.callback_query(F.data == "m_inventory")
async def cb_inventory_menu(call: CallbackQuery):
    case = await db.get_active_case(call.from_user.id)
    if case is None:
        await send_no_case(call)
        return
    if not await check_case_alive(case, call.message):
        await call.answer()
        return

    items = await db.get_inventory(case["id"])
    has_combo_items = any(it["id"] == case["combo_item_a"] for it in items) and \
        any(it["id"] == case["combo_item_b"] for it in items)
    show_combo = has_combo_items and not case["combo_done"]

    text = "🎒 <b>کوله‌پشتی</b>\n" + ("خالیه، برو یه جایی بگرد." if not items else "چیزی که همراهته:")
    await call.message.edit_text(text, reply_markup=kb.inventory_kb(items, show_combo))
    await call.answer()


@router.callback_query(F.data.startswith("inv_"))
async def cb_item_detail(call: CallbackQuery):
    item_id = int(call.data.removeprefix("inv_"))
    item = await db.get_item(item_id)
    if not item:
        await call.answer("این وسیله دیگه در دسترس نیست.", show_alert=True)
        return
    await call.message.edit_text(
        f"📦 <b>{item['name']}</b>\n\n{item['description']}",
        reply_markup=kb.item_detail_kb(item),
    )
    await call.answer()


@router.callback_query(F.data.startswith("use_"))
async def cb_use_item(call: CallbackQuery):
    item_id = int(call.data.removeprefix("use_"))
    case = await db.get_active_case(call.from_user.id)
    if case is None:
        await send_no_case(call)
        return

    item = await db.get_item(item_id)
    if not item or not item["consumable"]:
        await call.answer("این وسیله مصرف‌شدنی نیست.", show_alert=True)
        return

    field = item["consumable"]  # 'hunger' or 'thirst'
    new_value = min(100, case[field] + item["restore_amount"])
    await db.update_case(case["id"], **{field: new_value})
    await db.update_item(item_id, in_inventory=0)

    await call.answer(f"مصرفش کردی. {('گرسنگی' if field == 'hunger' else 'تشنگی')} کمی جبران شد.", show_alert=True)
    await cb_inventory_menu(call)


@router.callback_query(F.data == "combo_try")
async def cb_combo_try(call: CallbackQuery):
    case = await db.get_active_case(call.from_user.id)
    if case is None:
        await send_no_case(call)
        return

    await db.update_case(case["id"], combo_done=1, reputation=min(100, case["reputation"] + 10))
    await db.add_log(case["id"], case["day"], "🔗 دو تا سرنخ کلیدی رو کنار هم گذاشتی و یه نتیجه‌ی قطعی گرفتی.")

    case = await db.get_case(case["id"])
    await call.answer(case["combo_result"], show_alert=True)
    await cb_inventory_menu(call)


# --------------------------------------------------------------------------- #
# RADIO SIDE-QUEST (ASSEMBLY MINI-GAME)
# --------------------------------------------------------------------------- #

@router.callback_query(F.data == "m_radio")
async def cb_radio_menu(call: CallbackQuery):
    case = await db.get_active_case(call.from_user.id)
    if case is None:
        await send_no_case(call)
        return
    if not await check_case_alive(case, call.message):
        await call.answer()
        return

    inventory = await db.get_inventory(case["id"])
    parts = [it for it in inventory if it["assembly_step"] > 0]
    order = minigames.parse_order(case["assembly_order"])
    have_all = len(parts) >= 3

    if case["assembly_done"]:
        text = "🔧 <b>رادیوی قدیمی</b>\n\nقبلاً این رادیو رو با موفقیت تعمیر کردی."
    elif have_all:
        text = (
            "🔧 <b>رادیوی قدیمی</b>\n\n"
            f"هر ۳ قطعه رو داری: {', '.join(p['name'] for p in parts)}\n"
            "ولی نمی‌دونی به چه ترتیبی باید نصبشون کنی — باید امتحان کنی."
        )
    else:
        text = (
            "🔧 <b>رادیوی قدیمی</b>\n\n"
            f"یکی از مظنونین یه رادیوی خراب داره. اگه قطعاتش رو پیدا کنی و درست تعمیرش کنی، "
            f"اعتمادش بهت بیشتر می‌شه.\n\n"
            f"قطعات پیدا‌شده: {len(parts)}/3"
        )

    await call.message.edit_text(text, reply_markup=kb.radio_menu_kb(have_all, case["assembly_done"]))
    await call.answer()


@router.callback_query(F.data == "assembly_start")
async def cb_assembly_start(call: CallbackQuery, state: FSMContext):
    case = await db.get_active_case(call.from_user.id)
    if case is None:
        await send_no_case(call)
        return

    inventory = await db.get_inventory(case["id"])
    parts = [it for it in inventory if it["assembly_step"] > 0]
    if len(parts) < 3:
        await call.answer("هنوز هر ۳ قطعه رو نداری.", show_alert=True)
        return

    await state.set_state(AssemblyState.picking)
    await state.update_data(progress=0)
    await call.message.edit_text(
        "🔧 اولین قطعه‌ای که فکر می‌کنی باید نصب بشه رو انتخاب کن:",
        reply_markup=kb.assembly_parts_kb(parts),
    )
    await call.answer()


@router.callback_query(AssemblyState.picking, F.data.startswith("asm_"))
async def cb_assembly_pick(call: CallbackQuery, state: FSMContext):
    item_id = int(call.data.removeprefix("asm_"))
    case = await db.get_active_case(call.from_user.id)
    if case is None:
        await send_no_case(call)
        return

    item = await db.get_item(item_id)
    data = await state.get_data()
    progress = data["progress"]
    order = minigames.parse_order(case["assembly_order"])

    if minigames.assembly_check_next(order, progress, item["name"]):
        progress += 1
        if progress >= len(order):
            await db.update_case(case["id"], assembly_done=1,
                                  reputation=min(100, case["reputation"] + 10))
            owner = await db.get_suspect(case["radio_owner_suspect_id"])
            if owner:
                await db.update_suspect(owner["id"], trust=min(100, owner["trust"] + 25))
            await db.add_log(case["id"], case["day"], "🔧 رادیوی قدیمی رو با موفقیت تعمیر کردی!")
            await state.clear()
            await call.answer("🎉 رادیو روشن شد! اعتماد یکی از مظنونین بهت بیشتر شد.", show_alert=True)
            await cb_radio_menu(call)
            return

        await state.update_data(progress=progress)
        inventory = await db.get_inventory(case["id"])
        parts = [it for it in inventory if it["assembly_step"] > 0]
        await call.answer("درسته! ادامه بده.")
        await call.message.edit_text(
            f"🔧 قطعه‌ی بعدی رو انتخاب کن ({progress}/{len(order)}):",
            reply_markup=kb.assembly_parts_kb(parts),
        )
        return

    new_stamina = max(0, case["stamina"] - config.ASSEMBLY_FAIL_STAMINA_COST)
    await db.update_case(case["id"], stamina=new_stamina)
    await state.update_data(progress=0)
    await call.answer("❌ جور در نیومد، یه چیزی سوخت! از اول امتحان کن.", show_alert=True)

    case = await db.get_case(case["id"])
    if not await check_case_alive(case, call.message):
        await state.clear()
        return

    inventory = await db.get_inventory(case["id"])
    parts = [it for it in inventory if it["assembly_step"] > 0]
    await call.message.edit_text(
        "🔧 اولین قطعه رو دوباره انتخاب کن:",
        reply_markup=kb.assembly_parts_kb(parts),
    )


# --------------------------------------------------------------------------- #
# CASE LOG
# --------------------------------------------------------------------------- #

@router.callback_query(F.data == "m_log")
async def cb_log(call: CallbackQuery):
    case = await db.get_active_case(call.from_user.id)
    if case is None:
        await send_no_case(call)
        return

    logs = await db.get_logs(case["id"])
    if not logs:
        text = "📖 هنوز چیزی ثبت نشده."
    else:
        text = "📖 <b>گزارش پرونده</b>\n\n" + "\n".join(f"روز {l['day']}: {l['text']}" for l in logs)

    await call.message.edit_text(text, reply_markup=kb.back_kb())
    await call.answer()


# --------------------------------------------------------------------------- #
# DEDUCE / FINAL ACCUSATION
# --------------------------------------------------------------------------- #

@router.callback_query(F.data == "m_deduce")
async def cb_deduce_start(call: CallbackQuery):
    case = await db.get_active_case(call.from_user.id)
    if case is None:
        await send_no_case(call)
        return
    if not await check_case_alive(case, call.message):
        await call.answer()
        return

    suspects = await db.get_suspects(case["id"])
    await call.message.edit_text(
        "🧩 <b>نتیجه‌گیری نهایی</b>\n\n"
        "⚠️ این تصمیم قطعیه و پرونده رو می‌بنده. مطمئن شو قبلش بازجویی و کاوش کافی کردی.\n\n"
        "فکر می‌کنی قاتل کیه؟",
        reply_markup=kb.deduce_suspects_kb(suspects),
    )
    await call.answer()


@router.callback_query(F.data.startswith("dc_sus_"))
async def cb_deduce_suspect(call: CallbackQuery, state: FSMContext):
    suspect_id = int(call.data.removeprefix("dc_sus_"))
    await state.set_state(DeduceState.choosing_weapon)
    await state.update_data(suspect_id=suspect_id)
    await call.message.edit_text(
        "🔪 فکر می‌کنی از چه سلاحی استفاده کرده؟",
        reply_markup=kb.deduce_weapons_kb(),
    )
    await call.answer()


@router.callback_query(DeduceState.choosing_weapon, F.data.startswith("dc_wpn_"))
async def cb_deduce_weapon(call: CallbackQuery, state: FSMContext):
    weapon_index = int(call.data.removeprefix("dc_wpn_"))
    await state.update_data(weapon_index=weapon_index)
    await state.set_state(DeduceState.choosing_motive)
    await call.message.edit_text(
        "💭 فکر می‌کنی انگیزه‌اش چی بوده؟",
        reply_markup=kb.deduce_motives_kb(),
    )
    await call.answer()


@router.callback_query(DeduceState.choosing_motive, F.data.startswith("dc_mot_"))
async def cb_deduce_motive(call: CallbackQuery, state: FSMContext):
    motive_index = int(call.data.removeprefix("dc_mot_"))
    data = await state.get_data()
    suspect_id = data["suspect_id"]
    weapon_index = data["weapon_index"]
    await state.clear()

    case = await db.get_active_case(call.from_user.id)
    suspect = await db.get_suspect(suspect_id)
    culprit = await db.get_suspect(case["culprit_suspect_id"])

    culprit_correct = bool(suspect["is_culprit"])
    weapon_correct = gamedata.WEAPONS[weapon_index] == case["weapon"]
    motive_correct = gamedata.MOTIVES[motive_index] == case["motive"]
    combo_bonus = bool(case["combo_done"])

    score = sum([culprit_correct, weapon_correct, motive_correct, combo_bonus])

    if culprit_correct:
        new_status = "solved"
        new_rep = min(100, case["reputation"] + (25 if combo_bonus else 15))
    else:
        new_status = "failed"
        new_rep = max(0, case["reputation"] - 30)

    await db.update_case(case["id"], status=new_status, reputation=new_rep)

    if score >= 4:
        title = "🏆 پرونده کامل حل شد!"
        body = (
            f"با مدرک محکم روبروش وایسادی. {suspect['name']} شکست و به همه‌چیز اعتراف کرد. "
            f"سلاح ({case['weapon']}) و انگیزه ({case['motive']}) دقیقاً همونی بود که فکر می‌کردی. "
            f"شهر ازت به‌عنوان یه قهرمان یاد می‌کنه."
        )
    elif culprit_correct and score == 3:
        title = "✅ پرونده حل شد"
        body = (
            f"{suspect['name']} رو درست شناسایی کردی و بعد از فشار زیاد اعتراف کرد، "
            "هرچند همه‌ی جزئیات (سلاح/انگیزه) دقیق نبود. کافیه که حقیقت روشن شد."
        )
    elif culprit_correct:
        title = "🤔 پرونده نیمه‌حل شد"
        body = (
            f"آدم درست رو گرفتی، ولی مدارکت اونقدر قوی نبود. {suspect['name']} یه اعتراف نصفه‌ونیمه داد "
            "و وکیلش بقیه‌شو جمع کرد. حداقل حقیقت رو می‌دونی، حتی اگه رسمی نشه."
        )
    else:
        title = "💥 اشتباه بزرگ"
        body = (
            f"{suspect['name']} بی‌گناه بود. متهم کردنِ اشتباه یه غیرمقصر، اعتبارت رو نابود کرد و "
            f"قاتل واقعی ({culprit['name']}) هیچ‌وقت گیر نیفتاد."
        )

    await db.add_log(case["id"], case["day"], f"{title} — {body}")

    await call.message.edit_text(
        f"<b>{title}</b>\n\n{body}\n\n"
        f"سلاح واقعی: {case['weapon']}\nانگیزه واقعی: {case['motive']}\nقاتل واقعی: {culprit['name']}\n\n"
        "برای شروع یه پرونده‌ی جدید /newcase رو بزن.",
    )
    await call.answer()
