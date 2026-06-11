"""09:00 ertalabki risk-analitika hisobotini tayyorlaydi."""
import json
from datetime import date, datetime

import config
import database as db
import github as gh
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


_SESSION_CATS = {
    "10:00": "Restoran, Kafe",
    "13:00": "Klinika, Stomatologiya, Dorixona",
    "17:00": "Go'zallik, Fitness, Optika",
    "20:00": "Ta'lim, Mehmonxona, Bolalar bog'cha",
}


def _outreach_sessions_block() -> str:
    sessions = db.get_leads_stats_by_sessions()
    total_sent = sum(s["sent"] for s in sessions)
    if total_sent == 0:
        return "Bugun outreach yuborilmadi."

    lines = []
    for s in sessions:
        if s["sent"] == 0:
            continue
        cats = _SESSION_CATS.get(s["label"], "")
        lines.append(f"*{s['label']}* — {cats}")
        lines.append(f"  {s['sent']} ta yozildi, {s['replied']} ta javob berdi")
    return "\n".join(lines)


def _today_work_block() -> str:
    notes = db.get_today_notes()
    projs = {p["name"]: p["progress"] for p in db.active_projects()}

    if not notes and not projs:
        return "• Bugun hech qanday progress yozilmadi."

    lines = []
    for n in notes:
        proj = n["project_name"] or "Umumiy"
        add = f" (+{n['progress_add']:g}%)" if n["progress_add"] else ""
        lines.append(f"• {proj}{add}: {n['text']}")

    if not lines:
        for name, prog in projs.items():
            lines.append(f"• {name}: {prog:g}% (progress o'zgarmadi)")

    return "\n".join(lines) if lines else "• Bugun progress yozilmadi."


def _projects_status_block() -> str:
    projs = db.active_projects()
    if not projs:
        return "• Faol loyiha yo'q."
    lines = []
    for p in projs:
        days_left = max(0, p["duration_days"] - _days_passed(p["start_date"]))
        lines.append(f"• {p['name']}: {p['progress']:g}% — {days_left} kun qoldi")
    return "\n".join(lines)


def _clients_block() -> str:
    s = db.userbot_stats_today()
    lines = []
    if s["new_today"]:
        lines.append(f"• Yangi mijoz: {s['new_today']} ta")
    if s["active_today"]:
        lines.append(f"• Faol suhbat: {s['active_today']} ta")
    if s["escalated"]:
        lines.append(f"• Eskalatsiya: {s['escalated']} ta (e'tibor kerak!)")
    return "\n".join(lines) if lines else "• Bugun faol suhbat yo'q."


async def build_evening_summary() -> str:
    """22:00 — kechki xulosa: outreach sessiyalari + loyihalar + mijozlar."""
    now_str = datetime.now(config.TIMEZONE).strftime("%d-%m-%Y")

    outreach_block = _outreach_sessions_block()
    work_block = _today_work_block()

    return (
        f"🌙 *Kechki xulosa — {now_str}*\n\n"
        f"📤 *Outreach:*\n{outreach_block}\n\n"
        f"📁 *Bugun nima qilindi:*\n{work_block}"
    )


async def _github_block() -> str:
    commits = await gh.fetch_today_commits()
    if not config.GITHUB_USERNAME:
        return "• GITHUB_USERNAME sozlanmagan (Render env ga qo'shing)"
    if not commits:
        return "• Bugun commit topilmadi"
    lines = []
    for c in commits:
        lines.append(f"• [{c['repo']}] {c['message']} `{c['sha']}`")
    return "\n".join(lines)


async def build_auto_evening_report() -> str:
    """21:00 — avtomatik hisobot: GitHub commitlar + loyihalar + mijozlar + outreach."""
    now_str = datetime.now(config.TIMEZONE).strftime("%d-%m-%Y, %H:%M")

    projects_block = _projects_status_block()
    clients_block = _clients_block()
    outreach_block = _outreach_sessions_block()
    github_block = await _github_block()

    return (
        f"📊 *Kunlik holat — {now_str}*\n\n"
        f"💻 *Bugun commitlar:*\n{github_block}\n\n"
        f"📁 *Loyihalar:*\n{projects_block}\n\n"
        f"💬 *Mijozlar bugun:*\n{clients_block}\n\n"
        f"📤 *Outreach:*\n{outreach_block}"
    )
