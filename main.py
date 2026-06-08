"""Botni ishga tushirish: handlerlar, jadval, webhook va polling birga."""
import asyncio
import logging

import aiohttp
from aiohttp import web

import config
import database as db
import scheduler
import userbot
import webhook
import bot as _handlers  # noqa: F401  (import qilinishi handlerlarni ro'yxatga oladi)
from core import bot, dp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("main")


async def _start_webhook():
    app = webhook.make_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, config.WEBHOOK_HOST, config.WEBHOOK_PORT)
    await site.start()
    log.info("Webhook server: http://%s:%s/github", config.WEBHOOK_HOST, config.WEBHOOK_PORT)
    return runner


async def _keep_alive():
    """Render free tier ni uxlatmaslik uchun har 10 daqiqada o'ziga ping."""
    import os
    url = os.getenv("RENDER_EXTERNAL_URL", "")
    if not url:
        return
    await asyncio.sleep(60)
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                await session.get(url, timeout=aiohttp.ClientTimeout(total=10))
            except Exception:
                pass
            await asyncio.sleep(600)


async def main():
    db.init()
    log.info("Baza tayyor: %s", config.DB_PATH)

    if not config.DEVELOPER_CHAT_ID:
        log.warning("DEVELOPER_CHAT_ID hali sozlanmagan! Botga yozing — log'da chat ID chiqadi, "
                    "uni .env ga qo'shing.")

    scheduler.start()
    runner = await _start_webhook()

    # Userbot (ixtiyoriy — TELEGRAM_API_ID/HASH bo'lsa ishga tushadi)
    await userbot.init()

    tasks = [dp.start_polling(bot), _keep_alive()]
    if userbot.is_running():
        tasks.append(userbot._client.run_until_disconnected())

    try:
        await asyncio.gather(*tasks)
    finally:
        await userbot.disconnect()
        await runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("To'xtatildi.")
