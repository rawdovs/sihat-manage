"""APScheduler: 09:00 hisobot, 10:00/13:00/17:00/20:00 outreach, 21:00 auto-hisobot, 22:00 xulosa."""
import logging

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import config
import reports
from core import bot

log = logging.getLogger(__name__)
# pytz ishlatiladi — tizim tzdata ga bog'liq emas, Render da ham ishlaydi
_TZ = pytz.timezone("Asia/Tashkent")
_scheduler = AsyncIOScheduler(timezone=_TZ)


async def _morning_job():
    if not config.DEVELOPER_CHAT_ID:
        return
    text = await reports.build_morning_report()
    await bot.send_message(config.DEVELOPER_CHAT_ID, text)


async def _evening_job():
    """21:00 — avtomatik kunlik holat hisoboti. Hech narsa yozish shart emas."""
    if not config.DEVELOPER_CHAT_ID:
        return
    text = await reports.build_auto_evening_report()
    await bot.send_message(config.DEVELOPER_CHAT_ID, text, parse_mode="Markdown")


async def _evening_summary_job():
    """22:00 — bugun nima bo'ldi: loyihalar + outreach xulosa."""
    if not config.DEVELOPER_CHAT_ID:
        return
    text = await reports.build_evening_summary()
    await bot.send_message(config.DEVELOPER_CHAT_ID, text, parse_mode="Markdown")


async def _follow_up_job():
    """10:30 — javob bermagan kontaktlarga takroriy xabar (3 kun)."""
    import userbot
    await userbot.run_follow_ups()


# Har bir seans o'z kategoriyalari bilan
_OUTREACH_SESSIONS = {
    "10:00": ["restoran", "kafe"],
    "13:00": ["klinika", "stomatologiya", "dorixona"],
    "17:00": ["go'zallik salon", "fitness markaz", "optika"],
    "20:00": ["ta'lim markaz", "mehmonxona", "bolalar bog'chasi"],
}


async def _outreach_10():
    await _outreach_job("10:00")


async def _outreach_13():
    await _outreach_job("13:00")


async def _outreach_17():
    await _outreach_job("17:00")


async def _outreach_20():
    await _outreach_job("20:00")


async def _outreach_job(label: str):
    """Yangi leadlarga avtomatik xabar yuboradi (4 seans)."""
    import leads as leads_mod

    if not config.DEVELOPER_CHAT_ID:
        return

    categories = _OUTREACH_SESSIONS.get(label)
    log.info("Outreach sessiyasi boshlandi (%s) — %s", label, categories)
    sent, failed = await leads_mod.send_batch(limit=config.OUTREACH_DAILY, categories=categories)

    summary = (
        f"Outreach ({label}): {sent} ta yuborildi"
        + (f", {failed} ta xato" if failed else "")
    )
    log.info(summary)

    if sent == 0 and failed == 0:
        log.info("Outreach (%s): yangi lead yo'q — %s", label, categories)


def start():
    # misfire_grace_time=300 — bot 5 daqiqagacha kechikib startlansa ham job bajariladi
    _scheduler.add_job(_morning_job,
                       CronTrigger(hour=config.MORNING_HOUR, minute=0, timezone=_TZ),
                       id="morning", replace_existing=True, misfire_grace_time=300)
    _scheduler.add_job(_evening_job,
                       CronTrigger(hour=config.EVENING_HOUR, minute=0, timezone=_TZ),
                       id="evening", replace_existing=True, misfire_grace_time=300)
    _scheduler.add_job(_evening_summary_job,
                       CronTrigger(hour=22, minute=0, timezone=_TZ),
                       id="evening_summary", replace_existing=True, misfire_grace_time=300)
    _scheduler.add_job(_follow_up_job,
                       CronTrigger(hour=10, minute=30, timezone=_TZ),
                       id="follow_up", replace_existing=True, misfire_grace_time=300)
    _scheduler.add_job(_outreach_10,
                       CronTrigger(hour=10, minute=0, timezone=_TZ),
                       id="outreach_10", replace_existing=True, misfire_grace_time=300)
    _scheduler.add_job(_outreach_13,
                       CronTrigger(hour=13, minute=0, timezone=_TZ),
                       id="outreach_13", replace_existing=True, misfire_grace_time=300)
    _scheduler.add_job(_outreach_17,
                       CronTrigger(hour=17, minute=0, timezone=_TZ),
                       id="outreach_17", replace_existing=True, misfire_grace_time=300)
    _scheduler.add_job(_outreach_20,
                       CronTrigger(hour=20, minute=0, timezone=_TZ),
                       id="outreach_20", replace_existing=True, misfire_grace_time=300)

    _scheduler.start()
    log.info(
        "Jadval (Toshkent): %02d:00 hisobot | "
        "10:00(restoran) 13:00(klinika) 17:00(salon) 20:00(ta'lim) outreach | "
        "%02d:00 progress | 22:00 xulosa | 10:30 follow-up",
        config.MORNING_HOUR, config.EVENING_HOUR,
    )
