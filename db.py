"""
SHADOW CASE — database layer (aiosqlite).
"""

import asyncio
from datetime import datetime, timezone

import aiosqlite

import config
import gamedata

_lock = asyncio.Lock()
_conn: aiosqlite.Connection | None = None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def init_db():
    global _conn
    _conn = await aiosqlite.connect(config.DB_PATH)
    _conn.row_factory = aiosqlite.Row
    await _conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            status TEXT DEFAULT 'active',
            victim_name TEXT,
            weapon TEXT,
            motive TEXT,
            culprit_suspect_id INTEGER,
            combo_item_a INTEGER,
            combo_item_b INTEGER,
            combo_result TEXT,
            combo_done INTEGER DEFAULT 0,
            assembly_order TEXT,
            assembly_progress INTEGER DEFAULT 0,
            assembly_done INTEGER DEFAULT 0,
            radio_owner_suspect_id INTEGER,
            turn INTEGER DEFAULT 0,
            day INTEGER DEFAULT 1,
            max_days INTEGER DEFAULT 7,
            stamina INTEGER DEFAULT 100,
            hunger INTEGER DEFAULT 100,
            thirst INTEGER DEFAULT 100,
            health INTEGER DEFAULT 100,
            reputation INTEGER DEFAULT 50,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS suspects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER,
            name TEXT,
            personality TEXT,
            tell_bonus INTEGER DEFAULT 0,
            alibi TEXT,
            victim_line TEXT,
            is_culprit INTEGER DEFAULT 0,
            trust INTEGER DEFAULT 50,
            suspicion INTEGER DEFAULT 0,
            interviewed INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER,
            name TEXT,
            locked INTEGER DEFAULT 0,
            unlocked INTEGER DEFAULT 0,
            lock_code TEXT
        );

        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER,
            location_id INTEGER,
            name TEXT,
            description TEXT,
            is_key_clue INTEGER DEFAULT 0,
            found INTEGER DEFAULT 0,
            in_inventory INTEGER DEFAULT 0,
            consumable TEXT,
            restore_amount INTEGER DEFAULT 0,
            assembly_step INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER,
            day INTEGER,
            text TEXT,
            created_at TEXT
        );
        """
    )
    await _conn.commit()


async def ensure_user(user_id: int, username: str):
    async with _lock:
        await _conn.execute(
            "INSERT OR IGNORE INTO users (user_id, username, created_at) VALUES (?,?,?)",
            (user_id, username, now_iso()),
        )
        await _conn.commit()


async def get_active_case(user_id: int) -> aiosqlite.Row | None:
    cur = await _conn.execute(
        "SELECT * FROM cases WHERE user_id=? AND status='active' ORDER BY id DESC LIMIT 1",
        (user_id,),
    )
    return await cur.fetchone()


async def get_case(case_id: int) -> aiosqlite.Row | None:
    cur = await _conn.execute("SELECT * FROM cases WHERE id=?", (case_id,))
    return await cur.fetchone()


async def update_case(case_id: int, **fields):
    if not fields:
        return
    async with _lock:
        cols = ", ".join(f"{k}=?" for k in fields)
        await _conn.execute(f"UPDATE cases SET {cols} WHERE id=?", (*fields.values(), case_id))
        await _conn.commit()


async def create_case(user_id: int) -> int:
    data = gamedata.generate_new_case()

    async with _lock:
        cur = await _conn.execute(
            """INSERT INTO cases
               (user_id, status, victim_name, weapon, motive, max_days,
                stamina, hunger, thirst, health, reputation, created_at)
               VALUES (?, 'active', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id, data["victim_name"], data["weapon"], data["motive"],
                config.MAX_DAYS, config.START_STAMINA, config.START_HUNGER,
                config.START_THIRST, config.START_HEALTH, config.START_REPUTATION,
                now_iso(),
            ),
        )
        case_id = cur.lastrowid

        # locations
        location_ids = []
        for loc in data["locations"]:
            code_str = ",".join(str(x) for x in loc["code"]) if loc["locked"] else None
            c = await _conn.execute(
                "INSERT INTO locations (case_id, name, locked, unlocked, lock_code) VALUES (?,?,?,?,?)",
                (case_id, loc["name"], int(loc["locked"]), 0 if loc["locked"] else 1, code_str),
            )
            location_ids.append(c.lastrowid)

        # suspects
        suspect_ids = []
        culprit_suspect_id = None
        for s in data["suspects"]:
            c = await _conn.execute(
                """INSERT INTO suspects
                   (case_id, name, personality, tell_bonus, alibi, victim_line, is_culprit, trust, suspicion)
                   VALUES (?,?,?,?,?,?,?,?,0)""",
                (case_id, s["name"], s["personality"], s["tell_bonus"], s["alibi"],
                 s["victim_line"], int(s["is_culprit"]), config.START_TRUST),
            )
            suspect_ids.append(c.lastrowid)
            if s["is_culprit"]:
                culprit_suspect_id = c.lastrowid

        # items
        name_to_id = {}
        for it in data["items"]:
            loc_id = location_ids[it["location_index"]]
            c = await _conn.execute(
                """INSERT INTO items
                   (case_id, location_id, name, description, is_key_clue,
                    consumable, restore_amount, assembly_step)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (case_id, loc_id, it["name"], it["desc"], int(it.get("is_key_clue", False)),
                 it.get("consumable"), it.get("amount", 0), it.get("assembly_step", 0)),
            )
            name_to_id[it["name"]] = c.lastrowid

        combo_a_id = name_to_id.get(data["combo_a_name"])
        combo_b_id = name_to_id.get(data["combo_b_name"])
        radio_owner_suspect_id = suspect_ids[data["radio_owner_index"]]
        assembly_order_str = ",".join(data["assembly_order"])

        await _conn.execute(
            """UPDATE cases SET culprit_suspect_id=?, combo_item_a=?, combo_item_b=?,
               combo_result=?, assembly_order=?, radio_owner_suspect_id=? WHERE id=?""",
            (culprit_suspect_id, combo_a_id, combo_b_id, data["combo_result"],
             assembly_order_str, radio_owner_suspect_id, case_id),
        )
        await _conn.commit()

    await add_log(case_id, 1, f"🕵️ پرونده‌ی گمشدنِ «{data['victim_name']}» به تو واگذار شد. زمان محدوده — دقیق باش.")
    return case_id


async def get_locations(case_id: int):
    cur = await _conn.execute("SELECT * FROM locations WHERE case_id=? ORDER BY id", (case_id,))
    return await cur.fetchall()


async def get_location(location_id: int) -> aiosqlite.Row | None:
    cur = await _conn.execute("SELECT * FROM locations WHERE id=?", (location_id,))
    return await cur.fetchone()


async def update_location(location_id: int, **fields):
    async with _lock:
        cols = ", ".join(f"{k}=?" for k in fields)
        await _conn.execute(f"UPDATE locations SET {cols} WHERE id=?", (*fields.values(), location_id))
        await _conn.commit()


async def get_unfound_items(case_id: int, location_id: int):
    cur = await _conn.execute(
        "SELECT * FROM items WHERE case_id=? AND location_id=? AND found=0",
        (case_id, location_id),
    )
    return await cur.fetchall()


async def get_item(item_id: int) -> aiosqlite.Row | None:
    cur = await _conn.execute("SELECT * FROM items WHERE id=?", (item_id,))
    return await cur.fetchone()


async def update_item(item_id: int, **fields):
    async with _lock:
        cols = ", ".join(f"{k}=?" for k in fields)
        await _conn.execute(f"UPDATE items SET {cols} WHERE id=?", (*fields.values(), item_id))
        await _conn.commit()


async def get_inventory(case_id: int):
    cur = await _conn.execute(
        "SELECT * FROM items WHERE case_id=? AND in_inventory=1 ORDER BY id", (case_id,)
    )
    return await cur.fetchall()


async def get_suspects(case_id: int):
    cur = await _conn.execute("SELECT * FROM suspects WHERE case_id=? ORDER BY id", (case_id,))
    return await cur.fetchall()


async def get_suspect(suspect_id: int) -> aiosqlite.Row | None:
    cur = await _conn.execute("SELECT * FROM suspects WHERE id=?", (suspect_id,))
    return await cur.fetchone()


async def update_suspect(suspect_id: int, **fields):
    async with _lock:
        cols = ", ".join(f"{k}=?" for k in fields)
        await _conn.execute(f"UPDATE suspects SET {cols} WHERE id=?", (*fields.values(), suspect_id))
        await _conn.commit()


async def add_log(case_id: int, day: int, text: str):
    async with _lock:
        await _conn.execute(
            "INSERT INTO logs (case_id, day, text, created_at) VALUES (?,?,?,?)",
            (case_id, day, text, now_iso()),
        )
        await _conn.commit()


async def get_logs(case_id: int, limit: int = 15):
    cur = await _conn.execute(
        "SELECT day, text FROM logs WHERE case_id=? ORDER BY id DESC LIMIT ?",
        (case_id, limit),
    )
    return await cur.fetchall()
