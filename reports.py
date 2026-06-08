"""09:00 ertalabki risk-analitika hisobotini tayyorlaydi."""
import json
from datetime import date, datetime

import config
import database as db
import llm
from prompts import ADVICE_PROMPT, EVENING_SUMMARY_PROMPT, MORNING_REPORT_TEMPLATE


def _days_passed(start_iso: str) -> int:
    start = date.fromisoformat(start_iso)
    return (date.today() - start).days


def _analyze() -> dict:
    """Loyihalarni matematik tahlil qiladi, risklarni belgilaydi."""
    projects = []
    for p in db.active_projects():
        passed = _days_passed(p["start_date"])
        duration = max(1, p["duration_days"])
        time_ratio = passed / duration                 # vaqtning necha qismi o'tgan
        remaining = max(0, duration - passed)
        progress = p["progress"]
        # YUQORI RISK: vaqtning 70% dan ko'pi o'tgan, lekin progress < 50%
        high_risk = time_ratio > 0.70 and progress < 50
        # Bugun kerakli minimal progress (deadline'ni saqlash uchun)
        need_today = 0.0
        if high_risk and remaining > 0:
            need_today = round((100 - progress) / remaining, 1)
        projects.append({
            "name": p["name"],
            "progress": round(progress, 1),
            "days_left": remaining,
            "time_ratio": round(time_ratio, 2),
            "high_risk": high_risk,
            "need_today_percent": need_today,
            "last_activity": db.last_note(p["id"]),
            "open_tasks": json.loads(p["tasks"]),
        })
    advances, pending = db.finance_summary()
    return {"projects": projects, "advances": advances, "pending": pending}


def _risk_block(projects: list[dict]) -> str:
    lines = []
    any_risk = False
    for p in projects:
        if p["high_risk"]:
            any_risk = True
            open_n = len(p["open_tasks"])
            lines.append(
                f"⚠️ CRITICAL RISK — {p['name']}: {p['days_left']} kun qoldi, "
                f"progress {p['progress']}%. Grafikdan orqadasiz! Bugun kamida "
                f"{p['need_today_percent']}% progress qiling va {open_n} vazifani yopishga harakat qiling."
            )
        else:
            lines.append(
                f"{p['name']} — {p['days_left']} kun qoldi. Progress: {p['progress']}%."
            )
    if not lines:
        return "🟢 Faol loyihalar yo'q."
    if not any_risk:
        lines.append("🟢 Hamma loyihalar ideal grafik bo'yicha ketmoqda.")
    return "\n".join(lines)


def _projects_block(projects: list[dict]) -> str:
    if not projects:
        return "• Faol loyiha yo'q."
    out = []
    for p in projects:
        status = "🎉 Yakunlandi" if p["progress"] >= 100 else "Jarayonda"
        out.append(
            f"• 📁 {p['name']}: {p['progress']}% | Oxirgi faollik: {p['last_activity']} | Status: {status}"
        )
    return "\n".join(out)


def _client_block() -> str:
    stats = db.userbot_stats_today()
    if stats["total_clients"] == 0:
        return "• Hali birorta mijoz yo'q."
    lines = [
        f"• Jami mijozlar: {stats['total_clients']}",
        f"• Bugun yangi: {stats['new_today']}",
        f"• Bugun faol: {stats['active_today']}",
    ]
    if stats["escalated"]:
        lines.append(f"• ⚠️ Eskalatsiya kutmoqda: {stats['escalated']}")
    return "\n".join(lines)


async def build_morning_report() -> str:
    data = _analyze()
    data["client_stats"] = db.userbot_stats_today()
    try:
        advice = await llm.ask_text(
            ADVICE_PROMPT.format(data=json.dumps(data, ensure_ascii=False))
        )
    except Exception as e:
        advice = f"(Tavsiya yaratilmadi: {e})"

    return MORNING_REPORT_TEMPLATE.format(
        date=datetime.now(config.TIMEZONE).strftime("%d-%B"),
        risk_block=_risk_block(data["projects"]),
        projects_block=_projects_block(data["projects"]),
        client_block=_client_block(),
        advances=f"{data['advances']:g}",
        pending=f"{data['pending']:g}",
        advice=advice.strip(),
    )


async def build_evening_summary() -> str:
    """Kechki suhbat xulosasi — bugun nima bo'ldi."""
    stats = db.userbot_stats_today()
    projs = [dict(p) for p in db.active_projects()]
    data = {"client_stats": stats, "projects": projs}
    try:
        summary = await llm.ask_text(
            EVENING_SUMMARY_PROMPT.format(data=json.dumps(data, ensure_ascii=False))
        )
    except Exception as e:
        summary = f"(Xulosa yaratilmadi: {e})"
    return f"🌙 *Kechki xulosa*\n\n{summary.strip()}"
