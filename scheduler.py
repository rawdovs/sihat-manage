"""APScheduler: 09:00 hisobot, 21:00 progress so'rovi, 22:00 kechki xulosa."""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import config
import reports
from core import bot
from prompts import EVENING_PROMPT

log = logging.getLogger(__name__)
_scheduler = AsyncIOScheduler(timezone=config.TIMEZONE)


async def _morning_job():
    if not config.DEVELOPER_CHAT_ID:
        return
    text = await reports.build_morning_report()
    await bot.send_message(config.DEVELOPER_CHAT_ID, text)


async def _evening_job():
    if not config.DEVELOPER_CHAT_ID:
        return
    await bot.send_message(config.DEVELOPER_CHAT_ID, EVENING_PROMPT)


async def _evening_summary_job():
    """22:00 — bugun mijozlar bilan nima bo'ldi, qisqa xulosa."""
    if not config.DEVELOPER_CHAT_ID:
        return
    text = await reports.build_evening_summary()
    await bot.send_message(config.DEVELOPER_CHAT_ID, text, parse_mode="Markdown")


async def _follow_up_job():
    """10:00 — javob bermagan kontaktlarga takroriy xabar (3 kun)."""
    import userbot
    await userbot.run_follow_ups()


def start():
    _scheduler.add_job(_morning_job, CronTrigger(hour=config.MORNING_HOUR, minute=0),
                       id="morning", replace_existing=True)
    _scheduler.add_job(_evening_job, CronTrigger(hour=config.EVENING_HOUR, minute=0),
                       id="evening", replace_existing=True)
    _scheduler.add_job(_evening_summary_job, CronTrigger(hour=22, minute=0),
                       id="evening_summary", replace_existing=True)
    _scheduler.add_job(_follow_up_job, CronTrigger(hour=10, minute=0),
                       id="follow_up", replace_existing=True)
    _scheduler.start()
    log.info("Jadval: %02d:00 hisobot | %02d:00 progress | 22:00 xulosa | 10:00 follow-up",
             config.MORNING_HOUR, config.EVENING_HOUR)
