# -*- coding: utf-8 -*-
"""
War & Diplomacy Telegram Bot - single file build.
Run:  python bot.py
Needs BOT_TOKEN environment variable (see very bottom of this file for how to set it).
"""

import logging
import os
import random
import time
import asyncio
import sqlite3

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes



###############################################################################
# CONFIG / STATIC GAME DATA
###############################################################################

"""
Static game data: country pool, AI personalities, flavor text, random events.
Tweak everything here without touching the game logic.
"""

import random

# ---------------------------------------------------------------------------
# Countries available in the game. Feel free to add more (flag, name).
# ---------------------------------------------------------------------------
COUNTRY_POOL = [
    ("🇷🇺", "Russia"),
    ("🇺🇸", "USA"),
    ("🇩🇪", "Germany"),
    ("🇯🇵", "Japan"),
    ("🇫🇷", "France"),
    ("🇬🇧", "UK"),
    ("🇨🇳", "China"),
    ("🇮🇳", "India"),
    ("🇧🇷", "Brazil"),
    ("🇮🇹", "Italy"),
    ("🇹🇷", "Turkey"),
    ("🇰🇷", "South Korea"),
    ("🇪🇬", "Egypt"),
    ("🇨🇦", "Canada"),
    ("🇲🇽", "Mexico"),
    ("🇸🇦", "Saudi Arabia"),
]

# ---------------------------------------------------------------------------
# AI personalities and their tick-behavior weights.
# Each weight controls how likely that action is picked on an AI's turn.
# Keys: attack, trade, ally, spy, turtle(build army/walls), chat_only
# ---------------------------------------------------------------------------
PERSONALITIES = {
    "aggressive": {"attack": 0.45, "trade": 0.05, "ally": 0.05, "spy": 0.15, "turtle": 0.20, "chat_only": 0.10},
    "economic":   {"attack": 0.05, "trade": 0.40, "ally": 0.15, "spy": 0.10, "turtle": 0.10, "chat_only": 0.20},
    "defensive":  {"attack": 0.05, "trade": 0.15, "ally": 0.15, "spy": 0.05, "turtle": 0.45, "chat_only": 0.15},
    "diplomatic": {"attack": 0.05, "trade": 0.30, "ally": 0.35, "spy": 0.05, "turtle": 0.10, "chat_only": 0.15},
    "crazy":      {"attack": 0.30, "trade": 0.10, "ally": 0.15, "spy": 0.20, "turtle": 0.05, "chat_only": 0.20},
    "strategist": {"attack": 0.15, "trade": 0.20, "ally": 0.15, "spy": 0.20, "turtle": 0.20, "chat_only": 0.10},
}

DIFFICULTY_MULTIPLIER = {
    "easy": 0.7,
    "normal": 1.0,
    "hard": 1.3,
    "nightmare": 1.7,
}

# ---------------------------------------------------------------------------
# AI chat flavor lines. {name} gets replaced with the country name+flag.
# ---------------------------------------------------------------------------
CHAT_LINES = {
    "aggressive": [
        "{name}: We will never surrender.",
        "{name}: Our army grows stronger every day. Watch yourselves.",
        "{name}: Peace is for the weak.",
    ],
    "economic": [
        "{name}: Our economy is now the strongest in the region.",
        "{name}: Looking for good trade partners. Fair prices only.",
        "{name}: Markets are booming here.",
    ],
    "defensive": [
        "{name}: Our walls have never been breached.",
        "{name}: We seek no war, but we fear none either.",
        "{name}: Defense budget increased again.",
    ],
    "diplomatic": [
        "{name}: Who wants an alliance?",
        "{name}: Let's talk peace, friends.",
        "{name}: Cooperation benefits everyone.",
    ],
    "crazy": [
        "{name}: Maybe I attack. Maybe I don't. 😏",
        "{name}: Trust is overrated anyway.",
        "{name}: Something big is coming... just wait.",
    ],
    "strategist": [
        "{name}: Research completed.",
        "{name}: Patience wins wars.",
        "{name}: We are watching everyone closely.",
    ],
}

WORLD_NEWS_TEMPLATES = [
    "📰 World News\n{a} declared war on {b}.",
    "📰 Breaking News\nOil prices increased by {pct}%.",
    "📰 Global Report\nA rebellion has started inside {a}.",
    "📰 World News\n{a} and {b} signed a trade agreement.",
    "📰 Breaking News\nMassive protests reported in {a}.",
    "📰 Global Report\n{a}'s military budget reached record highs.",
    "📰 World News\nRefugee crisis worsens near {a} border.",
]

# ---------------------------------------------------------------------------
# Random world events. Each has a text template and an effect function
# applied in game_logic.apply_event (identified by "key").
# ---------------------------------------------------------------------------
RANDOM_EVENTS = [
    {"key": "flood", "text": "🌊 A massive flood hit {name}! Treasury and happiness drop.", "scope": "one"},
    {"key": "earthquake", "text": "🌍 An earthquake struck {name}! Military and treasury damaged.", "scope": "one"},
    {"key": "pandemic", "text": "🦠 A pandemic is spreading in {name}! Happiness plummets.", "scope": "one"},
    {"key": "economic_boom", "text": "📈 Economic boom in {name}! Treasury surges.", "scope": "one"},
    {"key": "gold_discovered", "text": "💰 Gold discovered in {name}! Treasury jumps.", "scope": "one"},
    {"key": "oil_crisis", "text": "🛢 Oil crisis hits {name}! Treasury and military spending drop.", "scope": "one"},
    {"key": "fuel_shortage", "text": "⛽ Fuel shortage in {name}! Military strength weakens.", "scope": "one"},
    {"key": "civil_war", "text": "⚔️ Civil unrest breaks out in {name}! Happiness and military drop sharply.", "scope": "one"},
    {"key": "food_shortage", "text": "🌾 Food shortage in {name}! Happiness drops.", "scope": "one"},
    {"key": "military_parade", "text": "🎖 {name} held a huge military parade! Happiness and morale rise.", "scope": "one"},
    {"key": "festival", "text": "🎉 A national festival is happening in {name}! Happiness rises.", "scope": "one"},
    {"key": "corruption", "text": "🕵️ Government corruption scandal rocks {name}! Treasury and happiness drop.", "scope": "one"},
]

def random_chat_line(personality: str, name: str) -> str:
    line = random.choice(CHAT_LINES.get(personality, CHAT_LINES["strategist"]))
    return line.format(name=name)


###############################################################################
# DATABASE LAYER (SQLite)
###############################################################################

"""
Tiny SQLite persistence layer. One DB file for the whole bot,
games are isolated by chat_id (one game per Telegram group).
"""

import sqlite3
import json
import time
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "warbot.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS games (
            chat_id INTEGER PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'setup',   -- setup | active | finished
            difficulty TEXT NOT NULL DEFAULT 'normal',
            tick_count INTEGER NOT NULL DEFAULT 0,
            created_at REAL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS countries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            flag TEXT NOT NULL,
            owner_user_id INTEGER,          -- NULL if AI-controlled
            owner_name TEXT,
            is_ai INTEGER NOT NULL DEFAULT 0,
            personality TEXT,               -- only set if is_ai
            treasury INTEGER NOT NULL DEFAULT 1000,
            military INTEGER NOT NULL DEFAULT 100,
            happiness INTEGER NOT NULL DEFAULT 70,
            tax_rate TEXT NOT NULL DEFAULT 'medium',  -- low|medium|high
            alive INTEGER NOT NULL DEFAULT 1,
            last_daily REAL DEFAULT 0,
            UNIQUE(chat_id, name)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS alliances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            country_a INTEGER NOT NULL,
            country_b INTEGER NOT NULL,
            trust INTEGER NOT NULL DEFAULT 50,
            status TEXT NOT NULL DEFAULT 'pending'   -- pending | active | broken
        )
    """)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Games
# ---------------------------------------------------------------------------
def create_game(chat_id: int, difficulty: str = "normal"):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO games (chat_id, status, difficulty, tick_count, created_at) "
        "VALUES (?, 'setup', ?, 0, ?)",
        (chat_id, difficulty, time.time()),
    )
    conn.commit()
    conn.close()


def get_game(chat_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM games WHERE chat_id = ?", (chat_id,)).fetchone()
    conn.close()
    return row


def set_game_status(chat_id: int, status: str):
    conn = get_conn()
    conn.execute("UPDATE games SET status = ? WHERE chat_id = ?", (status, chat_id))
    conn.commit()
    conn.close()


def set_difficulty(chat_id: int, difficulty: str):
    conn = get_conn()
    conn.execute("UPDATE games SET difficulty = ? WHERE chat_id = ?", (difficulty, chat_id))
    conn.commit()
    conn.close()


def bump_tick(chat_id: int):
    conn = get_conn()
    conn.execute("UPDATE games SET tick_count = tick_count + 1 WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()


def all_active_games():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM games WHERE status = 'active'").fetchall()
    conn.close()
    return rows


# ---------------------------------------------------------------------------
# Countries
# ---------------------------------------------------------------------------
def add_country(chat_id, name, flag, owner_user_id=None, owner_name=None,
                 is_ai=False, personality=None):
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO countries (chat_id, name, flag, owner_user_id, owner_name,
                                   is_ai, personality, treasury, military, happiness)
           VALUES (?, ?, ?, ?, ?, ?, ?, 1000, 100, 70)""",
        (chat_id, name, flag, owner_user_id, owner_name, int(is_ai), personality),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def get_countries(chat_id, alive_only=True):
    conn = get_conn()
    if alive_only:
        rows = conn.execute("SELECT * FROM countries WHERE chat_id = ? AND alive = 1", (chat_id,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM countries WHERE chat_id = ?", (chat_id,)).fetchall()
    conn.close()
    return rows


def get_country_by_name(chat_id, name):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM countries WHERE chat_id = ? AND LOWER(name) = LOWER(?)",
        (chat_id, name),
    ).fetchone()
    conn.close()
    return row


def get_country_by_owner(chat_id, user_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM countries WHERE chat_id = ? AND owner_user_id = ? AND alive = 1",
        (chat_id, user_id),
    ).fetchone()
    conn.close()
    return row


def get_country_by_id(country_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM countries WHERE id = ?", (country_id,)).fetchone()
    conn.close()
    return row


def update_country(country_id, **fields):
    if not fields:
        return
    conn = get_conn()
    keys = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [country_id]
    conn.execute(f"UPDATE countries SET {keys} WHERE id = ?", values)
    conn.commit()
    conn.close()


def adjust_country(country_id, treasury=0, military=0, happiness=0):
    conn = get_conn()
    row = conn.execute("SELECT treasury, military, happiness FROM countries WHERE id = ?",
                        (country_id,)).fetchone()
    if not row:
        conn.close()
        return
    new_treasury = max(0, row["treasury"] + treasury)
    new_military = max(0, row["military"] + military)
    new_happiness = max(0, min(100, row["happiness"] + happiness))
    conn.execute(
        "UPDATE countries SET treasury = ?, military = ?, happiness = ? WHERE id = ?",
        (new_treasury, new_military, new_happiness, country_id),
    )
    conn.commit()
    conn.close()
    return new_treasury, new_military, new_happiness


def kill_country(country_id):
    conn = get_conn()
    conn.execute("UPDATE countries SET alive = 0 WHERE id = ?", (country_id,))
    conn.commit()
    conn.close()


def taken_names(chat_id):
    conn = get_conn()
    rows = conn.execute("SELECT name FROM countries WHERE chat_id = ?", (chat_id,)).fetchall()
    conn.close()
    return {r["name"] for r in rows}


# ---------------------------------------------------------------------------
# Alliances
# ---------------------------------------------------------------------------
def propose_alliance(chat_id, a_id, b_id):
    conn = get_conn()
    conn.execute(
        "INSERT INTO alliances (chat_id, country_a, country_b, trust, status) VALUES (?, ?, ?, 50, 'pending')",
        (chat_id, a_id, b_id),
    )
    conn.commit()
    conn.close()


def get_pending_alliance(chat_id, a_id, b_id):
    conn = get_conn()
    row = conn.execute(
        """SELECT * FROM alliances WHERE chat_id = ? AND status = 'pending'
           AND ((country_a = ? AND country_b = ?) OR (country_a = ? AND country_b = ?))""",
        (chat_id, a_id, b_id, b_id, a_id),
    ).fetchone()
    conn.close()
    return row


def get_active_alliance(chat_id, a_id, b_id):
    conn = get_conn()
    row = conn.execute(
        """SELECT * FROM alliances WHERE chat_id = ? AND status = 'active'
           AND ((country_a = ? AND country_b = ?) OR (country_a = ? AND country_b = ?))""",
        (chat_id, a_id, b_id, b_id, a_id),
    ).fetchone()
    conn.close()
    return row


def set_alliance_status(alliance_id, status):
    conn = get_conn()
    conn.execute("UPDATE alliances SET status = ? WHERE id = ?", (status, alliance_id))
    conn.commit()
    conn.close()


def get_alliances_for(chat_id, country_id):
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM alliances WHERE chat_id = ? AND status = 'active'
           AND (country_a = ? OR country_b = ?)""",
        (chat_id, country_id, country_id),
    ).fetchall()
    conn.close()
    return rows


###############################################################################
# CORE GAME MECHANICS
###############################################################################

"""
Core game mechanics. Pure logic + DB calls, no Telegram-specific code here
(keeps handlers.py thin and this testable).
"""

import random
import time

TAX_INCOME = {"low": 40, "medium": 80, "high": 130}
TAX_HAPPINESS = {"low": +2, "medium": 0, "high": -3}

SPEND_CATEGORIES = {
    "military": {"military": 1},        # per 10 gold spent -> +military
    "education": {"happiness": 1},
    "healthcare": {"happiness": 1},
    "propaganda": {"happiness": 1},
    "research": {"military": 1},
}

DAILY_COOLDOWN = 20 * 60 * 60  # 20 hours, in seconds


def display_name(country_row) -> str:
    return f"{country_row['flag']} {country_row['name']}"


def economy_tick(country_row):
    """Passive income every game tick, based on tax rate."""
    income = TAX_INCOME.get(country_row["tax_rate"], 60)
    happiness_delta = TAX_HAPPINESS.get(country_row["tax_rate"], 0)
    # Low happiness slowly damages military morale
    military_delta = 0
    if country_row["happiness"] < 30:
        military_delta = -3
    adjust_country(country_row["id"], treasury=income, happiness=happiness_delta,
                       military=military_delta)


def set_tax(country_id, level: str):
    level = level.lower()
    if level not in TAX_INCOME:
        return False
    update_country(country_id, tax_rate=level)
    return True


def spend(country_row, category: str, amount: int):
    category = category.lower()
    if category not in SPEND_CATEGORIES:
        return None, "دسته‌بندی نامعتبره. یکی از این‌ها: military, education, healthcare, propaganda, research"
    if amount <= 0:
        return None, "مقدار باید مثبت باشه."
    if amount > country_row["treasury"]:
        return None, f"خزانه‌ت کافی نیست. موجودی فعلی: {country_row['treasury']}"

    effect = SPEND_CATEGORIES[category]
    gained = amount // 10
    treasury_delta = -amount
    military_delta = effect.get("military", 0) * gained
    happiness_delta = effect.get("happiness", 0) * gained

    adjust_country(country_row["id"], treasury=treasury_delta,
                       military=military_delta, happiness=happiness_delta)
    return (military_delta, happiness_delta), None


def claim_daily(country_row):
    now = time.time()
    last = country_row["last_daily"] or 0
    if now - last < DAILY_COOLDOWN:
        remaining = int(DAILY_COOLDOWN - (now - last))
        hrs = remaining // 3600
        mins = (remaining % 3600) // 60
        return None, f"⏳ جایزه روزانه هنوز آماده نیست. {hrs} ساعت و {mins} دقیقه دیگه امتحان کن."
    reward_gold = random.randint(80, 200)
    reward_happy = random.randint(1, 5)
    adjust_country(country_row["id"], treasury=reward_gold, happiness=reward_happy)
    update_country(country_row["id"], last_daily=now)
    return (reward_gold, reward_happy), None


# ---------------------------------------------------------------------------
# Espionage
# ---------------------------------------------------------------------------
def do_spy(spy_country, target_country):
    """Returns (success: bool, kind: str, detail: str)"""
    success_chance = 0.65
    if spy_country["military"] < target_country["military"] * 0.5:
        success_chance -= 0.15  # weak spies get caught more

    if random.random() > success_chance:
        # Failed / caught
        adjust_country(spy_country["id"], happiness=-2)
        return False, "caught", (
            f"🕵️ جاسوس {display_name(spy_country)} توی {display_name(target_country)} "
            f"دستگیر شد! رابطه بین دو کشور تیره‌تر شد."
        )

    outcome = random.choice(["reveal", "steal", "sabotage"])
    if outcome == "reveal":
        detail = (f"🕵️ جاسوسی {display_name(spy_country)} موفق شد!\n"
                  f"اطلاعات {display_name(target_country)}:\n"
                  f"💰 خزانه: ~{target_country['treasury']}\n"
                  f"⚔️ ارتش: ~{target_country['military']}")
        return True, "reveal", detail
    elif outcome == "steal":
        stolen = min(target_country["treasury"], random.randint(30, 120))
        adjust_country(target_country["id"], treasury=-stolen)
        adjust_country(spy_country["id"], treasury=stolen)
        detail = (f"🕵️ جاسوس {display_name(spy_country)} از خزانه {display_name(target_country)} "
                  f"{stolen} طلا دزدید!")
        return True, "steal", detail
    else:  # sabotage
        loss = random.randint(10, 25)
        adjust_country(target_country["id"], military=-loss)
        detail = (f"💣 خرابکاری موفق! {display_name(spy_country)} به تاسیسات نظامی "
                  f"{display_name(target_country)} حمله کرد. ارتش‌شون {loss} واحد ضعیف شد.")
        return True, "sabotage", detail


# ---------------------------------------------------------------------------
# Battles
# ---------------------------------------------------------------------------
def resolve_battle(attacker, defender):
    """
    Simple power-comparison battle with randomness.
    Returns dict with steps (list[str]) and final outcome summary.
    """
    steps = []
    steps.append(f"🚀 {display_name(attacker)} به {display_name(defender)} حمله کرد!")

    atk_power = attacker["military"] * random.uniform(0.8, 1.2)
    def_power = defender["military"] * random.uniform(0.8, 1.2) * 1.1  # defender's home advantage

    steps.append("✈️ جنگنده‌ها وارد نبرد شدند.")
    steps.append("💥 موشک‌ها شلیک شدند.")

    if defender["military"] > 0 and random.random() < 0.25:
        steps.append(f"🛡 پدافند هوایی {display_name(defender)} چند حمله رو دفع کرد.")

    attacker_losses = int(attacker["military"] * random.uniform(0.05, 0.20))
    defender_losses = int(defender["military"] * random.uniform(0.05, 0.20))

    won = atk_power > def_power
    if won:
        loot = int(defender["treasury"] * random.uniform(0.1, 0.25))
        defender_losses = int(defender["military"] * random.uniform(0.15, 0.35))
        happiness_hit_def = -random.randint(5, 15)
        happiness_hit_atk = random.randint(2, 6)

        adjust_country(attacker["id"], military=-attacker_losses, treasury=loot,
                           happiness=happiness_hit_atk)
        adjust_country(defender["id"], military=-defender_losses, treasury=-loot,
                           happiness=happiness_hit_def)

        steps.append(f"🏳️ {display_name(defender)} عقب‌نشینی کرد!")
        steps.append(f"🎖 {display_name(attacker)} پیروز شد و {loot} طلا غنیمت گرفت.")
    else:
        attacker_losses = int(attacker["military"] * random.uniform(0.15, 0.35))
        happiness_hit_atk = -random.randint(5, 15)
        happiness_hit_def = random.randint(2, 6)

        adjust_country(attacker["id"], military=-attacker_losses,
                           happiness=happiness_hit_atk)
        adjust_country(defender["id"], military=-defender_losses,
                           happiness=happiness_hit_def)

        steps.append(f"🛡 دفاع {display_name(defender)} موفقیت‌آمیز بود!")
        steps.append(f"❌ حمله {display_name(attacker)} شکست خورد.")

    # Check for elimination
    updated_defender = get_country_by_id(defender["id"])
    if updated_defender["military"] <= 0 and updated_defender["treasury"] <= 0:
        kill_country(defender["id"])
        steps.append(f"☠️ {display_name(defender)} دیگه توان جنگیدن نداره و از بازی حذف شد!")

    return {"steps": steps, "attacker_won": won}


# ---------------------------------------------------------------------------
# Alliances / betrayal
# ---------------------------------------------------------------------------
def betray(chat_id, betrayer_id, ally_id):
    alliance = get_active_alliance(chat_id, betrayer_id, ally_id)
    if not alliance:
        return False
    set_alliance_status(alliance["id"], "broken")
    # Betrayer gets a surprise-attack bonus, ally loses happiness/trust
    adjust_country(ally_id, happiness=-10)
    adjust_country(betrayer_id, military=15)  # surprise mobilization bonus
    return True


###############################################################################
# AI DECISION LOGIC
###############################################################################

"""
AI turn logic. Called periodically per game (see bot.py job queue).
Picks a weighted-random action for each AI country based on its personality.
"""

import random


def run_ai_tick(chat_id, difficulty="normal"):
    """
    Runs one decision for every living AI country in the game.
    Returns a list of human-readable message strings to post to the chat
    (chat lines, trade news, attack announcements, etc.)
    """
    messages = []
    countries = get_countries(chat_id, alive_only=True)
    ai_countries = [c for c in countries if c["is_ai"]]
    if not ai_countries:
        return messages

    mult = DIFFICULTY_MULTIPLIER.get(difficulty, 1.0)

    for ai in ai_countries:
        # Re-fetch in case it died earlier this loop
        ai = get_country_by_id(ai["id"])
        if not ai or not ai["alive"]:
            continue

        personality = ai["personality"] or "strategist"
        weights = PERSONALITIES.get(personality, PERSONALITIES["strategist"])
        action = _weighted_choice(weights)

        others = [c for c in countries if c["id"] != ai["id"] and c["alive"]]
        if not others:
            action = "chat_only"

        if action == "attack" and others:
            target = _pick_attack_target(ai, others)
            if target is None:
                action = "chat_only"
            else:
                # Boost AI military slightly by difficulty before resolving
                boosted_ai = dict(ai)
                boosted_ai["military"] = int(ai["military"] * mult)
                result = resolve_battle(boosted_ai, target)
                messages.append(f"⚔️ {display_name(ai)} به {display_name(target)} حمله کرد!")
                messages.extend(result["steps"][-2:])  # keep it short in group chat

        elif action == "trade":
            gain = random.randint(20, 60)
            adjust_country(ai["id"], treasury=gain)
            if random.random() < 0.5:
                messages.append(random_chat_line(personality, display_name(ai)))

        elif action == "ally" and others:
            target = random.choice(others)
            existing = get_active_alliance(chat_id, ai["id"], target["id"])
            pending = get_pending_alliance(chat_id, ai["id"], target["id"])
            if not existing and not pending:
                propose_alliance(chat_id, ai["id"], target["id"])
                messages.append(
                    f"🤝 {display_name(ai)} به {display_name(target)} "
                    f"پیشنهاد اتحاد داد. (با /alliance_accept {ai['name']} قبولش کن)"
                )

        elif action == "spy" and others:
            target = random.choice(others)
            success, kind, detail = do_spy(ai, target)
            if kind != "caught" or random.random() < 0.6:
                messages.append(detail)

        elif action == "turtle":
            gain_mil = random.randint(5, 15)
            adjust_country(ai["id"], military=gain_mil, treasury=-gain_mil * 3)

        else:  # chat_only
            if random.random() < 0.7:
                messages.append(random_chat_line(personality, display_name(ai)))

        # Crazy personality: small chance to betray a random ally regardless of action
        if personality == "crazy" and random.random() < 0.12:
            allies = get_alliances_for(chat_id, ai["id"])
            if allies:
                alliance = random.choice(allies)
                other_id = alliance["country_b"] if alliance["country_a"] == ai["id"] else alliance["country_a"]
                other = get_country_by_id(other_id)
                if other and other["alive"]:
                    betray(chat_id, ai["id"], other["id"])
                    messages.append(
                        f"🔪 غافلگیری! {display_name(ai)} به متحدش "
                        f"{display_name(other)} خیانت کرد!"
                    )

    return messages


def _weighted_choice(weights: dict) -> str:
    actions = list(weights.keys())
    probs = list(weights.values())
    return random.choices(actions, weights=probs, k=1)[0]


def _pick_attack_target(ai, others):
    """Prefer weaker targets (easier wins) with a little randomness."""
    if not others:
        return None
    others_sorted = sorted(others, key=lambda c: c["military"])
    pool = others_sorted[: max(1, len(others_sorted) // 2 + 1)]
    return random.choice(pool)


###############################################################################
# RANDOM WORLD EVENTS
###############################################################################

"""
Random world events (floods, booms, civil wars, ...) and flavor world-news
headlines. Both are cosmetic-plus-mechanical: events actually change country
stats, news lines are mostly flavor (occasionally referencing real state).
"""

import random

EVENT_EFFECTS = {
    "flood":            {"treasury": -60, "happiness": -8},
    "earthquake":       {"treasury": -80, "military": -15},
    "pandemic":         {"happiness": -20},
    "economic_boom":    {"treasury": +150},
    "gold_discovered":  {"treasury": +200},
    "oil_crisis":       {"treasury": -100},
    "fuel_shortage":     {"military": -20},
    "civil_war":        {"happiness": -25, "military": -20},
    "food_shortage":    {"happiness": -15},
    "military_parade":  {"happiness": +10},
    "festival":         {"happiness": +12},
    "corruption":       {"treasury": -70, "happiness": -10},
}


def trigger_random_event(chat_id):
    """Pick one random event, apply it to a random living country, return message."""
    countries = get_countries(chat_id, alive_only=True)
    if not countries:
        return None
    target = random.choice(countries)
    event = random.choice(RANDOM_EVENTS)
    effects = EVENT_EFFECTS.get(event["key"], {})

    adjust_country(
        target["id"],
        treasury=effects.get("treasury", 0),
        military=effects.get("military", 0),
        happiness=effects.get("happiness", 0),
    )

    text = event["text"].format(name=display_name(target))
    return text


def generate_world_news(chat_id):
    countries = get_countries(chat_id, alive_only=True)
    if len(countries) < 1:
        return None
    template = random.choice(WORLD_NEWS_TEMPLATES)
    a = random.choice(countries)
    b = random.choice(countries)
    tries = 0
    while b["id"] == a["id"] and len(countries) > 1 and tries < 5:
        b = random.choice(countries)
        tries += 1
    pct = random.randint(5, 40)
    return template.format(a=display_name(a), b=display_name(b), pct=pct)


###############################################################################
# TELEGRAM COMMAND HANDLERS
###############################################################################

import random
from telegram import Update
from telegram.ext import ContextTypes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def pick_random_country(chat_id):
    taken = taken_names(chat_id)
    available = [c for c in COUNTRY_POOL if c[1] not in taken]
    if not available:
        return None
    return random.choice(available)


async def require_game(update: Update):
    chat_id = update.effective_chat.id
    game = get_game(chat_id)
    if not game:
        await update.effective_message.reply_text(
            "هنوز بازی‌ای شروع نشده. اول با /newgame یه بازی بساز."
        )
        return None
    return game


async def require_my_country(update: Update):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    country = get_country_by_owner(chat_id, user_id)
    if not country:
        await update.effective_message.reply_text(
            "تو هنوز کشوری نداری! با /join وارد بازی شو."
        )
        return None
    return country


# ---------------------------------------------------------------------------
# Setup commands
# ---------------------------------------------------------------------------
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🌍 War & Diplomacy Bot\n\n"
        "شروع بازی:\n"
        "/newgame [easy|normal|hard|nightmare] — ساخت بازی جدید\n"
        "/join [نام کشور] — وارد شدن به بازی\n"
        "/startgame — شروع رسمی بازی (بقیه‌ی کشورها با AI پر می‌شن)\n\n"
        "اطلاعات:\n"
        "/status — وضعیت کشور خودت\n"
        "/world — وضعیت همه‌ی کشورها\n\n"
        "اقتصاد:\n"
        "/tax low|medium|high — تنظیم مالیات\n"
        "/spend category amount — هزینه (military, education, healthcare, propaganda, research)\n"
        "/daily — جایزه‌ی روزانه\n\n"
        "نظامی و جاسوسی:\n"
        "/attack نام کشور — حمله نظامی\n"
        "/spy نام کشور — عملیات جاسوسی\n\n"
        "دیپلماسی:\n"
        "/alliance نام کشور — پیشنهاد اتحاد\n"
        "/alliance_accept نام کشور — قبول اتحاد\n"
        "/betray نام کشور — خیانت به متحد\n"
    )
    await update.effective_message.reply_text(text)


async def cmd_newgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    difficulty = "normal"
    if context.args:
        arg = context.args[0].lower()
        if arg in DIFFICULTY_MULTIPLIER:
            difficulty = arg
    existing = get_game(chat_id)
    if existing and existing["status"] == "active":
        await update.effective_message.reply_text(
            "یه بازی همین الان توی این گروه فعاله! اگه می‌خوای از نو شروع کنی، اول باید یکی دستی ریست کنه."
        )
        return
    create_game(chat_id, difficulty)
    await update.effective_message.reply_text(
        f"🎮 بازی جدید ساخته شد! (سختی AI: {difficulty})\n"
        f"هر بازیکن با /join وارد بشه، بعد یکی /startgame رو بزنه.\n"
        f"برای دیدن کشورهای موجود: /countries"
    )


async def cmd_countries(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    taken = taken_names(chat_id)
    lines = ["🗺 کشورهای موجود:"]
    for flag, name in COUNTRY_POOL:
        mark = "❌" if name in taken else "✅"
        lines.append(f"{mark} {flag} {name}")
    await update.effective_message.reply_text("\n".join(lines))


async def cmd_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    game = await require_game(update)
    if not game:
        return
    if game["status"] != "setup":
        await update.effective_message.reply_text("بازی از قبل شروع شده، دیگه نمی‌تونی join کنی.")
        return

    chat_id = update.effective_chat.id
    user = update.effective_user
    already = get_country_by_owner(chat_id, user.id)
    if already:
        await update.effective_message.reply_text(
            f"تو از قبل کشور {display_name(already)} رو داری."
        )
        return

    if context.args:
        wanted_name = " ".join(context.args)
        match = next((c for c in COUNTRY_POOL if c[1].lower() == wanted_name.lower()), None)
        if not match:
            await update.effective_message.reply_text(
                "همچین کشوری توی لیست نیست. برای دیدن لیست: /countries"
            )
            return
        if match[1] in taken_names(chat_id):
            await update.effective_message.reply_text("این کشور قبلاً گرفته شده. یکی دیگه رو انتخاب کن.")
            return
        flag, name = match
    else:
        picked = pick_random_country(chat_id)
        if not picked:
            await update.effective_message.reply_text("همه‌ی کشورها گرفته شدن!")
            return
        flag, name = picked

    add_country(chat_id, name, flag, owner_user_id=user.id, owner_name=user.first_name)
    await update.effective_message.reply_text(
        f"🎉 {user.first_name} کنترل {flag} {name} رو به دست گرفت!"
    )


async def cmd_startgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    game = await require_game(update)
    if not game:
        return
    chat_id = update.effective_chat.id
    if game["status"] == "active":
        await update.effective_message.reply_text("بازی از قبل شروع شده.")
        return

    human_countries = get_countries(chat_id)
    if len(human_countries) == 0:
        await update.effective_message.reply_text("هنوز هیچ‌کس با /join وارد بازی نشده!")
        return

    # Fill remaining slots with AI countries (random personalities)
    taken = taken_names(chat_id)
    remaining = [c for c in COUNTRY_POOL if c[1] not in taken]
    random.shuffle(remaining)
    # Fill enough AI to make the world feel alive: at least 4, up to pool size
    target_ai_count = max(4, min(len(remaining), 8 - len(human_countries)))
    personalities = list(PERSONALITIES.keys())

    for flag, name in remaining[:target_ai_count]:
        personality = random.choice(personalities)
        add_country(chat_id, name, flag, is_ai=True, personality=personality)

    set_game_status(chat_id, "active")

    countries = get_countries(chat_id)
    lines = ["🚩 بازی شروع شد!\n", "کشورهای این دور:"]
    for c in countries:
        tag = "👤 بازیکن" if not c["is_ai"] else f"🤖 AI ({c['personality']})"
        lines.append(f"{c['flag']} {c['name']} — {tag}")
    lines.append("\nهر چند دقیقه یک‌بار اتفاقات، اخبار و حرکات AI توی گروه پست می‌شه.")
    lines.append("برای دستورات: /help")
    await update.effective_message.reply_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Info commands
# ---------------------------------------------------------------------------
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    country = await require_my_country(update)
    if not country:
        return
    text = (
        f"{display_name(country)}\n"
        f"💰 خزانه: {country['treasury']}\n"
        f"⚔️ ارتش: {country['military']}\n"
        f"😊 خوشحالی مردم: {country['happiness']}%\n"
        f"🧾 نرخ مالیات: {country['tax_rate']}"
    )
    await update.effective_message.reply_text(text)


async def cmd_world(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    countries = get_countries(chat_id)
    if not countries:
        await update.effective_message.reply_text("هنوز کشوری توی بازی نیست.")
        return
    lines = ["🌐 وضعیت جهان:"]
    for c in sorted(countries, key=lambda x: -x["military"]):
        owner = "🤖 AI" if c["is_ai"] else (c["owner_name"] or "بازیکن")
        lines.append(
            f"{c['flag']} {c['name']} ({owner}) — 💰{c['treasury']} ⚔️{c['military']} 😊{c['happiness']}%"
        )
    await update.effective_message.reply_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Economy
# ---------------------------------------------------------------------------
async def cmd_tax(update: Update, context: ContextTypes.DEFAULT_TYPE):
    country = await require_my_country(update)
    if not country:
        return
    if not context.args or context.args[0].lower() not in ("low", "medium", "high"):
        await update.effective_message.reply_text("استفاده: /tax low یا /tax medium یا /tax high")
        return
    level = context.args[0].lower()
    set_tax(country["id"], level)
    await update.effective_message.reply_text(f"🧾 نرخ مالیات {display_name(country)} به {level} تغییر کرد.")


async def cmd_spend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    country = await require_my_country(update)
    if not country:
        return
    if len(context.args) < 2:
        await update.effective_message.reply_text(
            "استفاده: /spend category amount\nمثال: /spend military 100"
        )
        return
    category = context.args[0]
    try:
        amount = int(context.args[1])
    except ValueError:
        await update.effective_message.reply_text("مقدار باید عدد باشه.")
        return

    result, error = spend(country, category, amount)
    if error:
        await update.effective_message.reply_text(f"❌ {error}")
        return
    mil, hap = result
    await update.effective_message.reply_text(
        f"✅ {amount} طلا صرف {category} شد.\n"
        f"⚔️ ارتش: {'+' if mil >= 0 else ''}{mil}\n"
        f"😊 خوشحالی: {'+' if hap >= 0 else ''}{hap}"
    )


async def cmd_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    country = await require_my_country(update)
    if not country:
        return
    result, error = claim_daily(country)
    if error:
        await update.effective_message.reply_text(error)
        return
    gold, happy = result
    await update.effective_message.reply_text(
        f"🎁 جایزه‌ی روزانه گرفتی: +{gold} طلا, +{happy}% خوشحالی!"
    )


# ---------------------------------------------------------------------------
# Military / espionage
# ---------------------------------------------------------------------------
async def cmd_attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    country = await require_my_country(update)
    if not country:
        return
    if not context.args:
        await update.effective_message.reply_text("استفاده: /attack نام کشور")
        return
    target_name = " ".join(context.args)
    chat_id = update.effective_chat.id
    target = get_country_by_name(chat_id, target_name)
    if not target or not target["alive"]:
        await update.effective_message.reply_text("همچین کشوری پیدا نشد یا از قبل نابود شده.")
        return
    if target["id"] == country["id"]:
        await update.effective_message.reply_text("نمی‌تونی به خودت حمله کنی!")
        return
    if country["military"] < 20:
        await update.effective_message.reply_text("ارتشت خیلی ضعیفه برای حمله (حداقل ۲۰ نیرو لازمه).")
        return

    result = resolve_battle(country, target)
    msg = await update.effective_message.reply_text(result["steps"][0])
    # Post remaining steps as a short "live battle" sequence
    import asyncio
    for step in result["steps"][1:]:
        await asyncio.sleep(1.5)
        await context.bot.send_message(chat_id=chat_id, text=step)


async def cmd_spy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    country = await require_my_country(update)
    if not country:
        return
    if not context.args:
        await update.effective_message.reply_text("استفاده: /spy نام کشور")
        return
    target_name = " ".join(context.args)
    chat_id = update.effective_chat.id
    target = get_country_by_name(chat_id, target_name)
    if not target or not target["alive"]:
        await update.effective_message.reply_text("همچین کشوری پیدا نشد یا از قبل نابود شده.")
        return
    if target["id"] == country["id"]:
        await update.effective_message.reply_text("نمی‌تونی از خودت جاسوسی کنی!")
        return

    success, kind, detail = do_spy(country, target)
    await update.effective_message.reply_text(detail)


# ---------------------------------------------------------------------------
# Diplomacy
# ---------------------------------------------------------------------------
async def cmd_alliance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    country = await require_my_country(update)
    if not country:
        return
    if not context.args:
        await update.effective_message.reply_text("استفاده: /alliance نام کشور")
        return
    target_name = " ".join(context.args)
    chat_id = update.effective_chat.id
    target = get_country_by_name(chat_id, target_name)
    if not target or not target["alive"]:
        await update.effective_message.reply_text("همچین کشوری پیدا نشد.")
        return
    if target["id"] == country["id"]:
        await update.effective_message.reply_text("نمی‌تونی با خودت متحد بشی!")
        return
    if get_active_alliance(chat_id, country["id"], target["id"]):
        await update.effective_message.reply_text("از قبل با این کشور متحدید.")
        return
    if get_pending_alliance(chat_id, country["id"], target["id"]):
        await update.effective_message.reply_text("پیشنهاد قبلاً ارسال شده، منتظر جواب بمون.")
        return

    propose_alliance(chat_id, country["id"], target["id"])
    await update.effective_message.reply_text(
        f"🤝 پیشنهاد اتحاد به {display_name(target)} ارسال شد."
    )


async def cmd_alliance_accept(update: Update, context: ContextTypes.DEFAULT_TYPE):
    country = await require_my_country(update)
    if not country:
        return
    if not context.args:
        await update.effective_message.reply_text("استفاده: /alliance_accept نام کشور")
        return
    target_name = " ".join(context.args)
    chat_id = update.effective_chat.id
    target = get_country_by_name(chat_id, target_name)
    if not target:
        await update.effective_message.reply_text("همچین کشوری پیدا نشد.")
        return

    pending = get_pending_alliance(chat_id, country["id"], target["id"])
    if not pending:
        await update.effective_message.reply_text("پیشنهاد اتحادی از این کشور در انتظار نیست.")
        return

    set_alliance_status(pending["id"], "active")
    await update.effective_message.reply_text(
        f"🤝✅ اتحاد بین {display_name(country)} و {display_name(target)} رسمی شد!"
    )


async def cmd_betray(update: Update, context: ContextTypes.DEFAULT_TYPE):
    country = await require_my_country(update)
    if not country:
        return
    if not context.args:
        await update.effective_message.reply_text("استفاده: /betray نام کشور")
        return
    target_name = " ".join(context.args)
    chat_id = update.effective_chat.id
    target = get_country_by_name(chat_id, target_name)
    if not target:
        await update.effective_message.reply_text("همچین کشوری پیدا نشد.")
        return

    ok = betray(chat_id, country["id"], target["id"])
    if not ok:
        await update.effective_message.reply_text("شما با این کشور اتحاد فعالی ندارید.")
        return
    await update.effective_message.reply_text(
        f"🔪 {display_name(country)} به متحدش {display_name(target)} خیانت کرد! "
        f"اعتماد از بین رفت."
    )


###############################################################################
# MAIN ENTRY POINT + BACKGROUND JOBS
###############################################################################

"""
Entry point. Wires up command handlers and the background "world is alive"
jobs (AI actions, random events, world news) for every active game.

Run with:  python bot.py
Token is read from the BOT_TOKEN environment variable (see .env.example).
"""

import logging
import os
import random

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Background jobs (one set scheduled per active chat/game)
# ---------------------------------------------------------------------------
AI_TICK_SECONDS = 3 * 60          # AI acts roughly every 3 minutes
NEWS_SECONDS = 7 * 60             # world news headline every ~7 minutes
EVENT_MIN_SECONDS = 10 * 60       # random events every 10-20 minutes
EVENT_MAX_SECONDS = 20 * 60


async def job_ai_tick(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    game = get_game(chat_id)
    if not game or game["status"] != "active":
        return
    # Passive tax income for every living country (human-controlled too)
    for country in get_countries(chat_id, alive_only=True):
        economy_tick(country)
    messages = run_ai_tick(chat_id, difficulty=game["difficulty"])
    bump_tick(chat_id)
    for m in messages:
        try:
            await context.bot.send_message(chat_id=chat_id, text=m)
        except Exception as e:
            logger.warning("Failed to send AI message: %s", e)


async def job_world_news(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    game = get_game(chat_id)
    if not game or game["status"] != "active":
        return
    news = generate_world_news(chat_id)
    if news:
        try:
            await context.bot.send_message(chat_id=chat_id, text=news)
        except Exception as e:
            logger.warning("Failed to send news: %s", e)


async def job_random_event(context: ContextTypes.DEFAULT_TYPE):
    """Fires a random event, then reschedules itself with a new random delay
    (10-20 min) so events don't happen on a perfectly fixed clock."""
    chat_id = context.job.chat_id
    game = get_game(chat_id)
    if game and game["status"] == "active":
        text = trigger_random_event(chat_id)
        if text:
            try:
                await context.bot.send_message(chat_id=chat_id, text=text)
            except Exception as e:
                logger.warning("Failed to send event: %s", e)

    # Reschedule next occurrence
    delay = random.randint(EVENT_MIN_SECONDS, EVENT_MAX_SECONDS)
    context.job_queue.run_once(job_random_event, when=delay, chat_id=chat_id,
                                name=f"event_{chat_id}")


def schedule_game_jobs(job_queue, chat_id):
    """Call this once right after a game becomes active (or on bot restart
    for games that were already active) to start its background loops."""
    # Avoid duplicate jobs if called twice
    for name in (f"ai_{chat_id}", f"news_{chat_id}", f"event_{chat_id}"):
        for job in job_queue.get_jobs_by_name(name):
            job.schedule_removal()

    job_queue.run_repeating(job_ai_tick, interval=AI_TICK_SECONDS, first=30,
                             chat_id=chat_id, name=f"ai_{chat_id}")
    job_queue.run_repeating(job_world_news, interval=NEWS_SECONDS, first=60,
                             chat_id=chat_id, name=f"news_{chat_id}")
    job_queue.run_once(job_random_event,
                        when=random.randint(EVENT_MIN_SECONDS, EVENT_MAX_SECONDS),
                        chat_id=chat_id, name=f"event_{chat_id}")


# ---------------------------------------------------------------------------
# Wrap /startgame so it also schedules jobs once the game goes active
# ---------------------------------------------------------------------------
async def cmd_startgame_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_startgame(update, context)
    chat_id = update.effective_chat.id
    game = get_game(chat_id)
    if game and game["status"] == "active":
        schedule_game_jobs(context.job_queue, chat_id)


async def on_startup(application: Application):
    """Resume background jobs for any game left 'active' from a previous run."""
    for game in all_active_games():
        schedule_game_jobs(application.job_queue, game["chat_id"])
        logger.info("Resumed jobs for chat %s", game["chat_id"])


async def on_error(update, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Unhandled exception while processing update %s", update, exc_info=context.error)


def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit(
            "BOT_TOKEN environment variable not set.\n"
            "Set it e.g.: export BOT_TOKEN=123456:ABC-your-token-here"
        )

    init_db()

    application = Application.builder().token(token).post_init(on_startup).build()

    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("start", cmd_help))
    application.add_handler(CommandHandler("newgame", cmd_newgame))
    application.add_handler(CommandHandler("countries", cmd_countries))
    application.add_handler(CommandHandler("join", cmd_join))
    application.add_handler(CommandHandler("startgame", cmd_startgame_wrapper))
    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(CommandHandler("world", cmd_world))
    application.add_handler(CommandHandler("tax", cmd_tax))
    application.add_handler(CommandHandler("spend", cmd_spend))
    application.add_handler(CommandHandler("daily", cmd_daily))
    application.add_handler(CommandHandler("attack", cmd_attack))
    application.add_handler(CommandHandler("spy", cmd_spy))
    application.add_handler(CommandHandler("alliance", cmd_alliance))
    application.add_handler(CommandHandler("alliance_accept", cmd_alliance_accept))
    application.add_handler(CommandHandler("betray", cmd_betray))
    application.add_error_handler(on_error)

    logger.info("Bot starting (polling)...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
