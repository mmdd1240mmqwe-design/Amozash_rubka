"""
SHADOW CASE — inline keyboard builders.
"""

from aiogram.utils.keyboard import InlineKeyboardBuilder

import gamedata


def main_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🔍 کاوش مکان‌ها", callback_data="m_explore")
    kb.button(text="🕵️ بازجویی از مظنونین", callback_data="m_suspects")
    kb.button(text="🎒 کوله‌پشتی", callback_data="m_inventory")
    kb.button(text="🧩 نتیجه‌گیری نهایی", callback_data="m_deduce")
    kb.button(text="🔧 قطعات رادیو", callback_data="m_radio")
    kb.button(text="📊 وضعیت", callback_data="m_status")
    kb.button(text="📖 گزارش پرونده", callback_data="m_log")
    kb.button(text="😴 استراحت", callback_data="m_rest")
    kb.adjust(2, 2, 2, 2)
    return kb.as_markup()


def back_kb(target: str = "back_main"):
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 بازگشت", callback_data=target)
    return kb.as_markup()


def locations_kb(locations):
    kb = InlineKeyboardBuilder()
    for loc in locations:
        icon = "🔒" if (loc["locked"] and not loc["unlocked"]) else "📍"
        kb.button(text=f"{icon} {loc['name']}", callback_data=f"loc_{loc['id']}")
    kb.button(text="🔙 بازگشت", callback_data="back_main")
    kb.adjust(1)
    return kb.as_markup()


def location_detail_kb(location):
    kb = InlineKeyboardBuilder()
    if location["locked"] and not location["unlocked"]:
        kb.button(text="🔓 باز کردن قفل", callback_data=f"lockpick_{location['id']}")
    else:
        kb.button(text="🔍 جستجوی این مکان", callback_data=f"search_{location['id']}")
    kb.button(text="🔙 بازگشت", callback_data="m_explore")
    kb.adjust(1)
    return kb.as_markup()


def digit_kb():
    kb = InlineKeyboardBuilder()
    for d in range(1, 7):
        kb.button(text=str(d), callback_data=f"dig_{d}")
    kb.button(text="❌ لغو", callback_data="m_explore")
    kb.adjust(6, 1)
    return kb.as_markup()


def suspects_kb(suspects):
    kb = InlineKeyboardBuilder()
    for s in suspects:
        tag = "🗣️" if s["interviewed"] else "❓"
        kb.button(text=f"{tag} {s['name']}", callback_data=f"sus_{s['id']}")
    kb.button(text="🔙 بازگشت", callback_data="back_main")
    kb.adjust(1)
    return kb.as_markup()


def suspect_detail_kb(suspect):
    kb = InlineKeyboardBuilder()
    kb.button(text="❓ درباره قربانی بپرس", callback_data=f"ask_victim_{suspect['id']}")
    kb.button(text="❓ درباره شب حادثه بپرس", callback_data=f"ask_alibi_{suspect['id']}")
    kb.button(text="📤 نشون دادن مدرک", callback_data=f"present_{suspect['id']}")
    kb.button(text="🔙 بازگشت", callback_data="m_suspects")
    kb.adjust(1)
    return kb.as_markup()


def present_items_kb(items, suspect_id):
    kb = InlineKeyboardBuilder()
    for it in items:
        kb.button(text=it["name"], callback_data=f"pres_{suspect_id}_{it['id']}")
    kb.button(text="🔙 بازگشت", callback_data=f"sus_{suspect_id}")
    kb.adjust(1)
    return kb.as_markup()


def inventory_kb(items, show_combo: bool):
    kb = InlineKeyboardBuilder()
    for it in items:
        icon = "🧩" if it["is_key_clue"] else ("🍽️" if it["consumable"] else "📦")
        kb.button(text=f"{icon} {it['name']}", callback_data=f"inv_{it['id']}")
    if show_combo:
        kb.button(text="🔗 ترکیب سرنخ‌ها", callback_data="combo_try")
    kb.button(text="🔙 بازگشت", callback_data="back_main")
    kb.adjust(1)
    return kb.as_markup()


def item_detail_kb(item, suspect_context=None):
    kb = InlineKeyboardBuilder()
    if item["consumable"]:
        kb.button(text="🍽️ مصرف کردن", callback_data=f"use_{item['id']}")
    kb.button(text="🔙 بازگشت", callback_data="m_inventory")
    kb.adjust(1)
    return kb.as_markup()


def deduce_suspects_kb(suspects):
    kb = InlineKeyboardBuilder()
    for s in suspects:
        kb.button(text=s["name"], callback_data=f"dc_sus_{s['id']}")
    kb.button(text="❌ لغو", callback_data="back_main")
    kb.adjust(1)
    return kb.as_markup()


def deduce_weapons_kb():
    kb = InlineKeyboardBuilder()
    for i, w in enumerate(gamedata.WEAPONS):
        kb.button(text=w, callback_data=f"dc_wpn_{i}")
    kb.adjust(1)
    return kb.as_markup()


def deduce_motives_kb():
    kb = InlineKeyboardBuilder()
    for i, m in enumerate(gamedata.MOTIVES):
        kb.button(text=m, callback_data=f"dc_mot_{i}")
    kb.adjust(1)
    return kb.as_markup()


def radio_menu_kb(can_assemble: bool, done: bool):
    kb = InlineKeyboardBuilder()
    if done:
        pass
    elif can_assemble:
        kb.button(text="🔧 شروع مونتاژ", callback_data="assembly_start")
    kb.button(text="🔙 بازگشت", callback_data="back_main")
    kb.adjust(1)
    return kb.as_markup()


def assembly_parts_kb(parts):
    kb = InlineKeyboardBuilder()
    for p in parts:
        kb.button(text=p["name"], callback_data=f"asm_{p['id']}")
    kb.button(text="❌ لغو", callback_data="m_radio")
    kb.adjust(1)
    return kb.as_markup()


def newcase_confirm_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ بله، پرونده جدید", callback_data="newcase_confirm")
    kb.button(text="🔙 نه، برگردون", callback_data="back_main")
    kb.adjust(1)
    return kb.as_markup()
