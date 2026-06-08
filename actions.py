"""Claude qaytargan JSON action'larni bazaga qo'llaydi."""
import database as db


def create_project(action: dict, client_chat=None, client_label=None) -> str:
    name = action.get("project_name", "Nomsiz loyiha")
    # price_uzs (so'mda) yoki eski price_usd ni qabul qiladi
    price = action.get("price_uzs") or action.get("price_usd", 0)
    days = action.get("duration_days", 0)
    tasks = action.get("tasks", [])
    pid = db.create_project(
        name=name, price_usd=price, duration_days=days, tasks=tasks,
        client_chat=client_chat, client_label=client_label,
    )
    advance = round(float(price) * db.config.ADVANCE_PERCENT / 100, 0)
    task_lines = "\n".join(f"   • {t}" for t in tasks) or "   • —"
    price_fmt = f"{int(price):,}".replace(",", " ")
    advance_fmt = f"{int(advance):,}".replace(",", " ")
    return (
        f"✅ Yangi loyiha yaratildi (#{pid})\n"
        f"📁 {name}\n"
        f"💵 Narx: {price_fmt} so'm  |  ⏳ Muddat: {days} kun\n"
        f"💰 Avans ({db.config.ADVANCE_PERCENT}%): {advance_fmt} so'm\n"
        f"📋 Vazifalar:\n{task_lines}"
    )


def update_progress(action: dict, source: str = "manual") -> str:
    name = action.get("project_name", "")
    add = float(action.get("add_progress_percent", 0))
    note = action.get("developer_note", "")
    proj = db.find_project_by_name(name)
    if not proj:
        # Aniq topilmasa, faqat izoh sifatida saqlaymiz
        db.add_note(f"[{name}] {note}", source=source, progress_add=add)
        return f"⚠️ '{name}' loyihasi topilmadi. Izoh saqlandi, lekin progress yangilanmadi."
    new = db.add_progress(proj["id"], add)
    db.add_note(note or "(izohsiz)", source=source, project_id=proj["id"], progress_add=add)
    done = "  🎉 Loyiha yakunlandi!" if new >= 100 else ""
    return f"📈 {proj['name']}: +{add:g}% → {new:g}%{done}\n📝 {note}"


def set_mode(action: dict) -> str:
    on = bool(action.get("deep_work", False))
    db.set_deep_work(on)
    if on:
        return "🔕 Deep Work yoqildi. Mijozlarga javoblar avval sizga tasdiqlash uchun keladi."
    return "🔔 Deep Work o'chirildi. Mijozlar bilan to'g'ridan-to'g'ri muloqot tiklandi."
