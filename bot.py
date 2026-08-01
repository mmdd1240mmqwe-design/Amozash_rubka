"""
GENESIS - Become A God
A Telegram civilization-god simulator.

Python 3.12 / aiogram 3.x / aiosqlite

Run:
    export BOT_TOKEN=xxxx
    python bot.py
"""

import asyncio
import logging
import os
import random
from datetime import datetime, timezone

import aiosqlite
from aiogram import Bot, Dispatcher, Router, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --------------------------------------------------------------------------- #
# CONFIG
# --------------------------------------------------------------------------- #

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DB_PATH = os.getenv("DB_PATH", "genesis.db")
TICK_SECONDS = int(os.getenv("TICK_SECONDS", "180"))  # how often the world ages

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("genesis")

router = Router()

# --------------------------------------------------------------------------- #
# GAME DATA
# --------------------------------------------------------------------------- #

TERRAIN_TYPES = {
    "ocean": "🌊 اقیانوس",
    "river": "🏞️ رودخانه",
    "mountain": "⛰️ کوه",
    "volcano": "🌋 آتشفشان",
    "forest": "🌳 جنگل",
    "desert": "🏜️ کویر",
    "snow": "❄️ برف",
    "island": "🏝️ جزیره",
}

LIFE_ORDER = ["none", "bacteria", "plants", "fish", "insects",
              "dinosaurs", "birds", "mammals", "humans"]

LIFE_LABEL = {
    "none": "هیچ حیاتی نیست",
    "bacteria": "🦠 باکتری",
    "plants": "🌱 گیاهان",
    "fish": "🐟 ماهی",
    "insects": "🐛 حشرات",
    "dinosaurs": "🦖 دایناسورها",
    "birds": "🐦 پرندگان",
    "mammals": "🐾 پستانداران",
    "humans": "🧑‍🤝‍🧑 انسان",
}

# requirement to evolve INTO this stage: dict of terrain-column -> min amount
LIFE_REQUIREMENTS = {
    "bacteria": {"ocean": 1},
    "plants": {"forest": 1},
    "fish": {"ocean": 2},
    "insects": {"forest": 2},
    "dinosaurs": {"forest": 3, "desert": 1},
    "birds": {"mountain": 1},
    "mammals": {"forest": 3},
    "humans": {"river": 1},
}

TECH_ORDER = ["stone_age", "bronze_age", "iron_age", "middle_ages", "gunpowder_age",
              "industrial_age", "electric_age", "information_age", "space_age"]

TECH_LABEL = {
    "stone_age": "🪨 عصر سنگ",
    "bronze_age": "🔺 عصر برنز",
    "iron_age": "⚔️ عصر آهن",
    "middle_ages": "🏰 قرون وسطی",
    "gunpowder_age": "💥 عصر باروت",
    "industrial_age": "🏭 عصر صنعتی",
    "electric_age": "💡 عصر برق",
    "information_age": "💻 عصر اطلاعات",
    "space_age": "🚀 عصر فضا",
}

POWERS = {
    "rain": {"label": "🌧️ باران", "cost": 10},
    "storm": {"label": "🌪️ طوفان", "cost": 15},
    "meteor": {"label": "☄️ شهاب‌سنگ", "cost": 40},
    "volcano": {"label": "🌋 فوران آتشفشان", "cost": 35},
    "blessing": {"label": "✨ برکت", "cost": 20},
    "curse": {"label": "💀 نفرین", "cost": 20},
    "miracle": {"label": "🌟 معجزه", "cost": 50},
}

CIV_EVENTS = [
    "🏘️ یک روستای جدید بنا شد.",
    "👑 یک پادشاه جدید تاج‌گذاری کرد.",
    "⛪ دین جدیدی در میان مردم پخش شد.",
    "🔬 اختراع بزرگی مردم را شگفت‌زده کرد.",
    "⚔️ جنگی میان دو قبیله درگرفت.",
    "🌾 برداشت محصول فوق‌العاده‌ای رخ داد.",
    "🏙️ یک شهر بزرگ بنا شد.",
    "🧭 کاشفان سرزمین جدیدی یافتند.",
    "🦠 طاعونی جمعیت را کاهش داد.",
    "📜 اولین قوانین نوشته شدند.",
    "💍 جشن بزرگ ازدواج سلطنتی برگزار شد.",
    "🔥 آتش‌سوزی بزرگ بخشی از سرزمین را ویران کرد.",
]

# --------------------------------------------------------------------------- #
# DATABASE
# --------------------------------------------------------------------------- #

_db_lock = asyncio.Lock()
_conn: aiosqlite.Connection | None = None


async def init_db():
    global _conn
    _conn = await aiosqlite.connect(DB_PATH)
    _conn.row_factory = aiosqlite.Row
    await _conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            god_name TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS worlds (
            user_id INTEGER PRIMARY KEY,
            world_name TEXT,
            stage TEXT DEFAULT 'void',
            year INTEGER DEFAULT 0,
            population INTEGER DEFAULT 0,
            faith INTEGER DEFAULT 0,
            divine_energy INTEGER DEFAULT 100,
            tech_era TEXT DEFAULT 'stone_age',
            life_stage TEXT DEFAULT 'none',
            ocean INTEGER DEFAULT 0,
            river INTEGER DEFAULT 0,
            mountain INTEGER DEFAULT 0,
            forest INTEGER DEFAULT 0,
            desert INTEGER DEFAULT 0,
            volcano INTEGER DEFAULT 0,
            snow INTEGER DEFAULT 0,
            island INTEGER DEFAULT 0,
            religion_name TEXT,
            religion_symbol TEXT,
            religion_color TEXT,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        );

        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            year INTEGER,
            event TEXT,
            created_at TEXT
        );
        """
    )
    await _conn.commit()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def get_or_create_world(user_id: int, username: str) -> aiosqlite.Row:
    async with _db_lock:
        cur = await _conn.execute("SELECT * FROM worlds WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if row:
            return row

        await _conn.execute(
            "INSERT OR IGNORE INTO users (user_id, username, god_name, created_at) VALUES (?,?,?,?)",
            (user_id, username, username or f"God{user_id}", now_iso()),
        )
        await _conn.execute(
            "INSERT INTO worlds (user_id, world_name) VALUES (?,?)",
            (user_id, f"دنیای {username or user_id}"),
        )
        await log_history(user_id, 0, "🌑 در تاریکی مطلق، یک خدای جدید بیدار شد و دنیایی خالی خلق کرد.")
        await _conn.commit()
        cur = await _conn.execute("SELECT * FROM worlds WHERE user_id=?", (user_id,))
        return await cur.fetchone()


async def get_world(user_id: int) -> aiosqlite.Row | None:
    cur = await _conn.execute("SELECT * FROM worlds WHERE user_id=?", (user_id,))
    return await cur.fetchone()


async def update_world(user_id: int, **fields):
    if not fields:
        return
    async with _db_lock:
        cols = ", ".join(f"{k}=?" for k in fields)
        await _conn.execute(f"UPDATE worlds SET {cols} WHERE user_id=?", (*fields.values(), user_id))
        await _conn.commit()


async def log_history(user_id: int, year: int, text: str):
    await _conn.execute(
        "INSERT INTO history (user_id, year, event, created_at) VALUES (?,?,?,?)",
        (user_id, year, text, now_iso()),
    )
    await _conn.commit()


async def get_history(user_id: int, limit: int = 12):
    cur = await _conn.execute(
        "SELECT year, event FROM history WHERE user_id=? ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    )
    return await cur.fetchall()


async def list_other_worlds(exclude_user_id: int, limit: int = 10):
    cur = await _conn.execute(
        """
        SELECT w.user_id, w.world_name, w.population, w.life_stage, u.god_name
        FROM worlds w JOIN users u ON u.user_id = w.user_id
        WHERE w.user_id != ?
        ORDER BY w.population DESC LIMIT ?
        """,
        (exclude_user_id, limit),
    )
    return await cur.fetchall()


async def all_civilization_worlds():
    cur = await _conn.execute("SELECT * FROM worlds WHERE life_stage='humans'")
    return await cur.fetchall()


async def regen_energy_all():
    async with _db_lock:
        await _conn.execute("UPDATE worlds SET divine_energy = MIN(divine_energy + 5, 200)")
        await _conn.commit()


# --------------------------------------------------------------------------- #
# STATES (religion creation)
# --------------------------------------------------------------------------- #

class ReligionForm(StatesGroup):
    name = State()
    symbol = State()
    color = State()


# --------------------------------------------------------------------------- #
# UI HELPERS
# --------------------------------------------------------------------------- #

def bar(value: int, maximum: int, length: int = 10) -> str:
    if maximum <= 0:
        maximum = 1
    filled = max(0, min(length, round(length * value / maximum)))
    return "▰" * filled + "▱" * (length - filled)


def main_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🌍 خلقت زمین", callback_data="menu_world")
    kb.button(text="🧬 حیات", callback_data="menu_life")
    kb.button(text="⚡ قدرت‌های الهی", callback_data="menu_power")
    kb.button(text="⛪ مذهب", callback_data="menu_religion")
    kb.button(text="📜 تاریخ جهان", callback_data="menu_history")
    kb.button(text="👥 دنیاهای دیگر", callback_data="menu_multiplayer")
    kb.button(text="📊 وضعیت", callback_data="menu_status")
    kb.adjust(2, 2, 2, 1)
    return kb.as_markup()


def back_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 بازگشت", callback_data="back_main")
    return kb.as_markup()


async def status_text(w: aiosqlite.Row) -> str:
    life = LIFE_LABEL.get(w["life_stage"], w["life_stage"])
    tech = TECH_LABEL.get(w["tech_era"], w["tech_era"])
    terrains = ", ".join(
        f"{TERRAIN_TYPES[t]}×{w[t]}" for t in TERRAIN_TYPES if w[t] > 0
    ) or "هیچ"
    religion = w["religion_name"] or "بدون دین"
    return (
        f"🪐 <b>{w['world_name']}</b>\n"
        f"سال: <b>{w['year']}</b>  |  مرحله: <b>{w['stage']}</b>\n\n"
        f"👥 جمعیت: <b>{w['population']}</b>\n"
        f"🙏 ایمان: {bar(w['faith'], 100)} {w['faith']}/100\n"
        f"⚡ انرژی الهی: {bar(w['divine_energy'], 200)} {w['divine_energy']}/200\n\n"
        f"🧬 حیات: {life}\n"
        f"🛠️ فناوری: {tech}\n"
        f"🗺️ زمین‌ها: {terrains}\n"
        f"⛪ دین: {religion}\n"
    )


# --------------------------------------------------------------------------- #
# HANDLERS - basic
# --------------------------------------------------------------------------- #

@router.message(CommandStart())
async def cmd_start(message: Message):
    w = await get_or_create_world(message.from_user.id, message.from_user.first_name)
    await message.answer(
        "🌌 <b>GENESIS — Become A God</b>\n\n"
        "تو اکنون یک خدا هستی. دنیای تو در تاریکی مطلق منتظر توست.\n"
        "زمین بساز، حیات بیافرین، تمدنی بنا کن که خودش رشد می‌کند... و بعد سرنوشتش را با قدرت‌های الهی رقم بزن.\n\n"
        f"{await status_text(w)}",
        reply_markup=main_menu_kb(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "دستورات:\n"
        "/start - شروع بازی / منوی اصلی\n"
        "/status - وضعیت دنیای تو\n"
        "/history - تاریخچه دنیای تو\n"
    )


@router.message(Command("status"))
async def cmd_status(message: Message):
    w = await get_or_create_world(message.from_user.id, message.from_user.first_name)
    await message.answer(await status_text(w), reply_markup=main_menu_kb())


@router.callback_query(F.data == "back_main")
@router.callback_query(F.data == "menu_status")
async def cb_main(call: CallbackQuery):
    w = await get_or_create_world(call.from_user.id, call.from_user.first_name)
    await call.message.edit_text(await status_text(w), reply_markup=main_menu_kb())
    await call.answer()


# --------------------------------------------------------------------------- #
# HANDLERS - world / terrain creation
# --------------------------------------------------------------------------- #

@router.callback_query(F.data == "menu_world")
async def cb_world_menu(call: CallbackQuery):
    kb = InlineKeyboardBuilder()
    for key, label in TERRAIN_TYPES.items():
        kb.button(text=label, callback_data=f"terrain_{key}")
    kb.button(text="🔙 بازگشت", callback_data="back_main")
    kb.adjust(2)
    await call.message.edit_text(
        "🌍 <b>خلقت زمین</b>\nهر زمین که بسازی، شرایط لازم برای ظهور حیات و تمدن را فراهم می‌کند.",
        reply_markup=kb.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("terrain_"))
async def cb_create_terrain(call: CallbackQuery):
    terrain = call.data.removeprefix("terrain_")
    if terrain not in TERRAIN_TYPES:
        await call.answer()
        return

    w = await get_or_create_world(call.from_user.id, call.from_user.first_name)
    new_val = w[terrain] + 1
    new_stage = "terrain" if w["stage"] == "void" else w["stage"]
    await update_world(call.from_user.id, **{terrain: new_val}, stage=new_stage)

    if w[terrain] == 0:
        await log_history(
            call.from_user.id, w["year"],
            f"{TERRAIN_TYPES[terrain]} برای اولین بار در این دنیا شکل گرفت."
        )

    await call.answer(f"{TERRAIN_TYPES[terrain]} خلق شد!")
    w2 = await get_world(call.from_user.id)
    await call.message.edit_text(await status_text(w2), reply_markup=main_menu_kb())


# --------------------------------------------------------------------------- #
# HANDLERS - life evolution
# --------------------------------------------------------------------------- #

def next_life_stage(current: str) -> str | None:
    idx = LIFE_ORDER.index(current)
    if idx + 1 < len(LIFE_ORDER):
        return LIFE_ORDER[idx + 1]
    return None


def requirement_met(w: aiosqlite.Row, stage: str) -> bool:
    reqs = LIFE_REQUIREMENTS.get(stage, {})
    return all(w[col] >= amt for col, amt in reqs.items())


def requirement_text(stage: str) -> str:
    reqs = LIFE_REQUIREMENTS.get(stage, {})
    return "، ".join(f"{TERRAIN_TYPES[c]}≥{a}" for c, a in reqs.items()) or "—"


@router.callback_query(F.data == "menu_life")
async def cb_life_menu(call: CallbackQuery):
    w = await get_or_create_world(call.from_user.id, call.from_user.first_name)
    nxt = next_life_stage(w["life_stage"])
    kb = InlineKeyboardBuilder()

    if nxt is None:
        desc = "حیات در این دنیا به بالاترین مرحله (انسان) رسیده و تمدن اکنون خودش رشد می‌کند."
    elif requirement_met(w, nxt):
        desc = f"شرایط برای تکامل به «{LIFE_LABEL[nxt]}» فراهم است!"
        kb.button(text=f"✅ تکامل به {LIFE_LABEL[nxt]}", callback_data="evolve_life")
    else:
        desc = f"برای تکامل به «{LIFE_LABEL[nxt]}» نیاز داری: {requirement_text(nxt)}"

    kb.button(text="🔙 بازگشت", callback_data="back_main")
    kb.adjust(1)
    await call.message.edit_text(
        f"🧬 <b>حیات</b>\nمرحله فعلی: {LIFE_LABEL[w['life_stage']]}\n\n{desc}",
        reply_markup=kb.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data == "evolve_life")
async def cb_evolve(call: CallbackQuery):
    w = await get_or_create_world(call.from_user.id, call.from_user.first_name)
    nxt = next_life_stage(w["life_stage"])
    if not nxt or not requirement_met(w, nxt):
        await call.answer("شرایط تکامل هنوز فراهم نیست.", show_alert=True)
        return

    updates = {"life_stage": nxt}
    if nxt == "humans":
        updates["stage"] = "civilization"
        updates["population"] = max(w["population"], 10)
    await update_world(call.from_user.id, **updates)
    await log_history(call.from_user.id, w["year"], f"حیات تکامل یافت: ظهور {LIFE_LABEL[nxt]} در دنیا.")

    if nxt == "humans":
        await log_history(call.from_user.id, w["year"],
                           "🧑‍🤝‍🧑 نخستین انسان‌ها ظاهر شدند. اکنون تمدن خودش زندگی می‌کند و رشد می‌کند.")

    await call.answer(f"تکامل یافت: {LIFE_LABEL[nxt]} 🎉", show_alert=True)
    w2 = await get_world(call.from_user.id)
    await call.message.edit_text(await status_text(w2), reply_markup=main_menu_kb())


# --------------------------------------------------------------------------- #
# HANDLERS - divine powers
# --------------------------------------------------------------------------- #

@router.callback_query(F.data == "menu_power")
async def cb_power_menu(call: CallbackQuery):
    kb = InlineKeyboardBuilder()
    for key, meta in POWERS.items():
        kb.button(text=f"{meta['label']} ({meta['cost']}⚡)", callback_data=f"power_{key}")
    kb.button(text="🔙 بازگشت", callback_data="back_main")
    kb.adjust(2)
    await call.message.edit_text(
        "⚡ <b>قدرت‌های الهی</b>\nهر قدرت انرژی الهی مصرف می‌کند. انرژی به مرور بازیابی می‌شود.",
        reply_markup=kb.as_markup(),
    )
    await call.answer()


def apply_power_effect(power: str, w: aiosqlite.Row) -> tuple[int, int, str]:
    """returns (new_population, faith_delta, history_text)"""
    pop = w["population"]
    faith_delta = 0
    if power == "rain":
        pop = int(pop * 1.05) + 1
        faith_delta = 1
        text = "🌧️ باران الهی محصولات را پربار کرد و جمعیت افزایش یافت."
    elif power == "storm":
        pop = int(pop * 0.95)
        text = "🌪️ طوفانی شدید بخشی از سرزمین را ویران کرد."
    elif power == "meteor":
        pop = int(pop * 0.7)
        text = "☄️ شهاب‌سنگی عظیم بر دنیا فرود آمد و ویرانی به بار آورد."
    elif power == "volcano":
        pop = int(pop * 0.75)
        text = "🌋 آتشفشانی فوران کرد و زمین‌های اطراف را دگرگون ساخت."
    elif power == "blessing":
        pop = int(pop * 1.08) + 1
        faith_delta = 5
        text = "✨ برکتی الهی بر مردم فرود آمد؛ رفاه و ایمان افزایش یافت."
    elif power == "curse":
        pop = int(pop * 0.85)
        faith_delta = -5
        text = "💀 نفرینی سرزمین را فراگرفت؛ ایمان مردم کاهش یافت."
    elif power == "miracle":
        pop = int(pop * 1.1) + 1
        faith_delta = 15
        text = "🌟 معجزه‌ای بزرگ رخ داد و باور مردم به خدای خود چند برابر شد."
    else:
        text = "اتفاقی نامشخص رخ داد."
    return max(pop, 0), faith_delta, text


@router.callback_query(F.data.startswith("power_"))
async def cb_use_power(call: CallbackQuery):
    power = call.data.removeprefix("power_")
    if power not in POWERS:
        await call.answer()
        return

    w = await get_or_create_world(call.from_user.id, call.from_user.first_name)
    cost = POWERS[power]["cost"]
    if w["divine_energy"] < cost:
        await call.answer("انرژی الهی کافی نیست! کمی صبر کن تا بازیابی شود.", show_alert=True)
        return

    new_pop, faith_delta, text = apply_power_effect(power, w)
    new_faith = max(0, min(100, w["faith"] + faith_delta))
    await update_world(
        call.from_user.id,
        population=new_pop,
        faith=new_faith,
        divine_energy=w["divine_energy"] - cost,
    )
    await log_history(call.from_user.id, w["year"], text)

    await call.answer(POWERS[power]["label"] + " اعمال شد!")
    w2 = await get_world(call.from_user.id)
    await call.message.edit_text(await status_text(w2), reply_markup=main_menu_kb())


# --------------------------------------------------------------------------- #
# HANDLERS - religion (FSM)
# --------------------------------------------------------------------------- #

@router.callback_query(F.data == "menu_religion")
async def cb_religion_menu(call: CallbackQuery, state: FSMContext):
    w = await get_or_create_world(call.from_user.id, call.from_user.first_name)
    if w["religion_name"]:
        kb = InlineKeyboardBuilder()
        kb.button(text="🔄 بازتعریف دین", callback_data="religion_new")
        kb.button(text="🔙 بازگشت", callback_data="back_main")
        kb.adjust(1)
        await call.message.edit_text(
            f"⛪ <b>دین این دنیا</b>\n"
            f"نام: {w['religion_name']}\nنماد: {w['religion_symbol']}\nرنگ مقدس: {w['religion_color']}\n"
            f"ایمان فعلی مردم: {w['faith']}/100",
            reply_markup=kb.as_markup(),
        )
    else:
        kb = InlineKeyboardBuilder()
        kb.button(text="➕ آفرینش دین جدید", callback_data="religion_new")
        kb.button(text="🔙 بازگشت", callback_data="back_main")
        kb.adjust(1)
        await call.message.edit_text(
            "⛪ <b>دین</b>\nهنوز دینی در این دنیا آفریده نشده است.",
            reply_markup=kb.as_markup(),
        )
    await call.answer()


@router.callback_query(F.data == "religion_new")
async def cb_religion_new(call: CallbackQuery, state: FSMContext):
    await state.set_state(ReligionForm.name)
    await call.message.edit_text("نام دین را بفرست (پیام متنی):", reply_markup=back_kb())
    await call.answer()


@router.message(ReligionForm.name)
async def religion_set_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text[:64])
    await state.set_state(ReligionForm.symbol)
    await message.answer("نماد مقدس دین را بفرست (یک ایموجی یا کلمه کوتاه):")


@router.message(ReligionForm.symbol)
async def religion_set_symbol(message: Message, state: FSMContext):
    await state.update_data(symbol=message.text[:32])
    await state.set_state(ReligionForm.color)
    await message.answer("رنگ مقدس دین را بفرست (مثلاً: طلایی):")


@router.message(ReligionForm.color)
async def religion_set_color(message: Message, state: FSMContext):
    data = await state.update_data(color=message.text[:32])
    await state.clear()
    await update_world(
        message.from_user.id,
        religion_name=data["name"],
        religion_symbol=data["symbol"],
        religion_color=data["color"],
        faith=30,
    )
    w = await get_or_create_world(message.from_user.id, message.from_user.first_name)
    await log_history(message.from_user.id, w["year"], f"⛪ دین «{data['name']}» بنیان‌گذاری شد.")
    await message.answer(f"دین «{data['name']}» آفریده شد! ایمان اولیه: 30/100", reply_markup=main_menu_kb())


# --------------------------------------------------------------------------- #
# HANDLERS - history
# --------------------------------------------------------------------------- #

@router.message(Command("history"))
@router.callback_query(F.data == "menu_history")
async def cb_history(update):
    user_id = update.from_user.id
    rows = await get_history(user_id, limit=12)
    if not rows:
        text = "📜 هنوز هیچ رویدادی ثبت نشده است."
    else:
        lines = [f"سال {r['year']}: {r['event']}" for r in rows]
        text = "📜 <b>تاریخچه جهان</b>\n\n" + "\n\n".join(lines)

    if isinstance(update, CallbackQuery):
        await update.message.edit_text(text, reply_markup=back_kb())
        await update.answer()
    else:
        await update.answer(text)


# --------------------------------------------------------------------------- #
# HANDLERS - multiplayer
# --------------------------------------------------------------------------- #

@router.callback_query(F.data == "menu_multiplayer")
async def cb_multiplayer_menu(call: CallbackQuery):
    worlds = await list_other_worlds(call.from_user.id)
    kb = InlineKeyboardBuilder()
    if not worlds:
        text = "👥 هنوز هیچ خدای دیگری وارد بازی نشده. رفیقت را دعوت کن!"
    else:
        text = "👥 <b>دنیاهای دیگر</b>\nیکی را انتخاب کن تا بتوانی برکت، نفرین یا بلا بفرستی:"
        for r in worlds:
            kb.button(
                text=f"{r['god_name']} — {LIFE_LABEL.get(r['life_stage'],'?')} ({r['population']} نفر)",
                callback_data=f"visit_{r['user_id']}",
            )
    kb.button(text="🔙 بازگشت", callback_data="back_main")
    kb.adjust(1)
    await call.message.edit_text(text, reply_markup=kb.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("visit_"))
async def cb_visit_world(call: CallbackQuery):
    target_id = int(call.data.removeprefix("visit_"))
    w = await get_world(target_id)
    if not w:
        await call.answer("این دنیا دیگر وجود ندارد.", show_alert=True)
        return
    kb = InlineKeyboardBuilder()
    kb.button(text="✨ ارسال برکت", callback_data=f"act_bless_{target_id}")
    kb.button(text="💀 ارسال نفرین", callback_data=f"act_curse_{target_id}")
    kb.button(text="☄️ ارسال بلا", callback_data=f"act_disaster_{target_id}")
    kb.button(text="🔙 بازگشت", callback_data="menu_multiplayer")
    kb.adjust(1)
    await call.message.edit_text(
        f"🪐 <b>{w['world_name']}</b>\n"
        f"جمعیت: {w['population']} | حیات: {LIFE_LABEL.get(w['life_stage'],'?')} | ایمان: {w['faith']}/100\n\n"
        "چه بلایی/عطیه‌ای برایشان بفرستم؟",
        reply_markup=kb.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("act_"))
async def cb_multiplayer_action(call: CallbackQuery):
    _, action, target_id = call.data.split("_", 2)
    target_id = int(target_id)

    my_world = await get_or_create_world(call.from_user.id, call.from_user.first_name)
    cost = 25
    if my_world["divine_energy"] < cost:
        await call.answer("انرژی الهی کافی برای دخالت در دنیای دیگر نداری.", show_alert=True)
        return

    target = await get_world(target_id)
    if not target:
        await call.answer("این دنیا دیگر وجود ندارد.", show_alert=True)
        return

    god_name = call.from_user.first_name or "ناشناس"
    if action == "bless":
        new_pop = int(target["population"] * 1.1) + 1
        new_faith = min(100, target["faith"] + 5)
        text = f"✨ خدای دیگری به نام «{god_name}» بر این دنیا برکت فرستاد."
    elif action == "curse":
        new_pop = int(target["population"] * 0.9)
        new_faith = max(0, target["faith"] - 5)
        text = f"💀 خدای دیگری به نام «{god_name}» این دنیا را نفرین کرد."
    else:  # disaster
        new_pop = int(target["population"] * 0.6)
        new_faith = target["faith"]
        text = f"☄️ خدای دیگری به نام «{god_name}» بلایی مخرب بر این دنیا فرستاد."

    await update_world(target_id, population=max(new_pop, 0), faith=new_faith)
    await log_history(target_id, target["year"], text)
    await update_world(call.from_user.id, divine_energy=my_world["divine_energy"] - cost)

    await call.answer("انجام شد!", show_alert=True)
    await cb_multiplayer_menu(call)


# --------------------------------------------------------------------------- #
# BACKGROUND WORLD TICK
# --------------------------------------------------------------------------- #

async def world_tick_loop(bot: Bot):
    while True:
        try:
            await asyncio.sleep(TICK_SECONDS)
            await regen_energy_all()
            worlds = await all_civilization_worlds()
            for w in worlds:
                year_delta = random.randint(1, 5)
                new_year = w["year"] + year_delta

                growth = random.uniform(0.98, 1.12)
                if w["faith"] > 50:
                    growth += 0.02
                new_pop = max(0, int(w["population"] * growth) + random.randint(0, 3))

                updates = {"year": new_year, "population": new_pop}

                # chance to advance tech era
                idx = TECH_ORDER.index(w["tech_era"])
                if idx < len(TECH_ORDER) - 1 and random.random() < 0.15:
                    new_era = TECH_ORDER[idx + 1]
                    updates["tech_era"] = new_era
                    await log_history(w["user_id"], new_year,
                                       f"🛠️ تمدن وارد {TECH_LABEL[new_era]} شد.")

                await update_world(w["user_id"], **updates)

                if random.random() < 0.6:
                    event = random.choice(CIV_EVENTS)
                    await log_history(w["user_id"], new_year, event)

        except Exception as e:  # keep the loop alive no matter what
            log.exception("world tick error: %s", e)


# --------------------------------------------------------------------------- #
# ENTRYPOINT
# --------------------------------------------------------------------------- #

async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is not set.")

    await init_db()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    asyncio.create_task(world_tick_loop(bot))

    log.info("GENESIS bot starting...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
