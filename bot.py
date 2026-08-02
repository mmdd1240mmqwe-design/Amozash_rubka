"""
SHADOW CASE — entrypoint.

Run:
    export BOT_TOKEN=xxxx
    python bot.py
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

import config
import db
from handlers import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("shadowcase")


async def main():
    if not config.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is not set.")

    await db.init_db()

    bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    log.info("SHADOW CASE bot starting...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
