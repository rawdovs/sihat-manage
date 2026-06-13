"""Telegram handlerlari: dasturchi va mijoz xabarlarini boshqarish."""
import json
import logging
import os
import re
import tempfile
from collections import defaultdict, deque
from datetime import date

from aiogram import F
from aiogram.filters import Command, CommandStart
from aiogram.types import (CallbackQuery, InlineKeyboardButton,
                           InlineKeyboardMarkup, Message)

import actions
import config
import database as db
import llm
import outreach
import reports
import transcribe
import userbot
from core import bot, dp

# @username yoki +telefon (ixtiyoriy keyin matn)
_CONTACT_RE = re.compile(r'^(@[\w]{5,}|\+\d{9,15})(\s+(.+))?$', re.DOTALL)

log = logging.getLogger(__name__)

# Har bir chat uchun oxirgi 20 ta xabar (kontekst uchun)
_history: dict[int, deque] = defaultdict(lambda: deque(maxlen=10))


def is_developer(chat_id: int) -> bool:
    return config.DEVELOPER_CHAT_ID and chat_id == config.DEVELOPER_CHAT_ID


def _context_for(chat_id: int) -> str:
    """Claude'ga beriladigan vaziyat konteksti."""
    parts = []
    if is_developer(chat_id):
        parts.append("Hozir DASTURCHINING o'zi bilan gaplashyapsan (PM/arxitektor rejimi).")
    else:
        client_proj = db.find_project_by_client_chat(chat_id)
        if client_proj:
            parts.append(
                f"BU MIJOZNING LOYIHASI: '{client_proj['name']}' — "
                f"{client_proj['progress']:g}% tayyor, {client_proj['duration_days']} kunlik. "
                "Bu MAVJUD MIJOZ — sotuv strategiyasini ISHLATMA, 'biznesingiz nima?' DEMA."
            )
        else:
            parts.append("Hozir MIJOZ bilan gaplashyapsan (sotuv rejimi). Dasturchi nomidan gapir.")
        if db.deep_work_on():
            parts.append("Dasturchi DEEP WORK rejimida — javobni to'g'ridan-to'g'ri yuborma, "
                         "PENDING_APPROVAL action bilan tasdiqlashga yubor.")
    projs = db.active_projects()
    if projs:
        lst = "; ".join(f"{p['name']} ({p['progress']:g}%)" for p in projs)
        parts.append(f"Barcha faol loyihalar: {lst}.")
    if config.CARD_NUMBER:
        parts.append(f"To'lov kartasi: {config.CARD_NUMBER}")
    if config.PORTFOLIO_LINK:
        parts.append(f"PORTFOLIO_LINK: {config.PORTFOLIO_LINK}")
    return "\n".join(parts)


async def _run_llm(chat_id: int, user_text: str) -> tuple[str, dict | None]:
    hist = _history[chat_id]
    hist.append({"role": "user", "content": user_text})
    raw = await llm.ask(list(hist), extra_system=_context_for(chat_id))
    visible, action = llm.extract_action(raw)
    hist.append({"role": "assistant", "content": raw})
    return visible, action


async def _apply_action(action: dict, message: Message, visible: str) -> str | None:
    """Action'ni qo'llaydi. Mijozga yuboriladigan matnni qaytaradi (yoki None)."""
    kind = action.get("action")
    chat_id = message.chat.id
    label = f"@{message.from_user.username}" if message.from_user.username else str(chat_id)

    if kind == "CREATE_PROJECT":
        summary = actions.create_project(action, client_chat=chat_id, client_label=label)
        await bot.send_message(config.DEVELOPER_CHAT_ID, summary)
        return visible  # mijozga tasdiq matnini ham yuboramiz

    if kind == "UPDATE_PROGRESS":
        summary = actions.update_progress(action, source="manual")
        await bot.send_message(config.DEVELOPER_CHAT_ID, summary)
        return None  # bu dasturchi konteksti, alohida matn shart emas

    if kind == "SET_MODE":
        summary = actions.set_mode(action)
        await bot.send_message(config.DEVELOPER_CHAT_ID, summary)
        return None

    if kind == "PENDING_APPROVAL":
        # Mijozga yubormaymiz — dasturchiga tasdiqlashга yuboramiz
        approval_id = db.create_approval(chat_id, visible)
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Yuborish", callback_data=f"appr:{approval_id}:ok"),
            InlineKeyboardButton(text="❌ Bekor", callback_data=f"appr:{approval_id}:no"),
        ]])
        await bot.send_message(
            config.DEVELOPER_CHAT_ID,
            f"📨 Mijoz {label} uchun javob tayyor (tasdiqlang):\n\n{visible}",
            reply_markup=kb,
        )
        return None  # mijoz hozircha javob olmaydi

    return visible


@dp.message(CommandStart())
async def on_start(message: Message):
    # Buyruq sintaksisini ko'rsatmaymiz — faqat tabiiy salom
    if is_developer(message.chat.id):
        await message.answer(
            "Assalomu alaykum, <b>Abdurashidov Abdufozil</b>\n\n"
            "Loyihalar, mijozlar va moliya nazoratda. Bugun nimadan boshlaymiz?",
            parse_mode="HTML"
        )
    else:
        await message.answer(
            "Assalomu alaykum! Loyihangiz bo'yicha gaplashamizmi? "
            "Qanday yechim qidiryapsiz?"
        )
    log.info("Chat ID: %s (username: %s)", message.chat.id, message.from_user.username)


@dp.message(Command("status"))
async def on_status(message: Message):
    if not is_developer(message.chat.id):
        return
    projs = db.active_projects()
    stats = db.userbot_stats_today()
    adv, pend = db.finance_summary()
    mode = "DEEP WORK" if db.deep_work_on() else "Normal"
    ub = "Ulangan" if userbot.is_running() else "Ulanmagan"

    def _days_left(p):
        passed = (date.today() - date.fromisoformat(p["start_date"])).days
        return max(0, p["duration_days"] - passed)

    proj_lines = "\n".join(
        f"  • {p['name']}: {p['progress']:g}% ({_days_left(p)} kun qoldi)"
        for p in projs
    ) or "  Faol loyihalar yo'q"

    await message.answer(
        f"⚙️ TIZIM HOLATI\n\n"
        f"🔧 Rejim: {mode}\n"
        f"📡 Userbot: {ub}\n\n"
        f"📁 LOYIHALAR:\n{proj_lines}\n\n"
        f"💰 MOLIYA:\n"
        f"  Avanslar: ${adv:g}\n"
        f"  Kutilmoqda: ${pend:g}\n\n"
        f"👥 MIJOZLAR (bugun):\n"
        f"  Jami: {stats['total_clients']}\n"
        f"  Yangi: {stats['new_today']}\n"
        f"  Faol: {stats['active_today']}\n"
        f"  Eskalatsiya: {stats['escalated']}"
    )


@dp.message(Command("clients"))
async def on_clients(message: Message):
    if not is_developer(message.chat.id):
        return
    rows = db._conn.execute(
        "SELECT name, username, message_count, status, last_activity, last_message "
        "FROM userbot_chats ORDER BY last_activity DESC LIMIT 15"
    ).fetchall()
    if not rows:
        await message.answer("Hali birorta mijoz yo'q.")
        return
    lines = ["👥 So'nggi 15 ta mijoz:\n"]
    for r in rows:
        uname = f"@{r['username']}" if r["username"] else "—"
        status = " ⚠️" if r["status"] == "escalated" else ""
        lines.append(
            f"👤 {r['name']} ({uname}){status}\n"
            f"  💬 {r['message_count']} xabar | 📅 {r['last_activity'][:10]}\n"
            f"  \"{(r['last_message'] or '')[:60]}\"\n"
        )
    await message.answer("\n".join(lines))


@dp.message(Command("projects"))
async def on_projects(message: Message):
    if not is_developer(message.chat.id):
        return
    projs = db.active_projects()
    if not projs:
        await message.answer("Faol loyihalar yo'q.")
        return
    lines = ["📁 Faol loyihalar:\n"]
    for p in projs:
        passed = (date.today() - date.fromisoformat(p["start_date"])).days
        left = max(0, p["duration_days"] - passed)
        tasks = json.loads(p["tasks"])
        open_t = len(tasks)
        risk = "⚠️ " if left < 3 and p["progress"] < 80 else ""
        lines.append(
            f"{risk}📌 {p['name']}\n"
            f"  📊 Progress: {p['progress']:g}% | ⏳ Qoldi: {left} kun\n"
            f"  💵 Narx: ${p['price_usd']:g} | 📋 Vazifalar: {open_t} ta\n"
            f"  👤 Mijoz: {p['client_label'] or '—'}\n"
        )
    await message.answer("\n".join(lines))


@dp.message(Command("testleads"))
async def on_testleads(message: Message):
    if not is_developer(message.chat.id):
        return
    import leads as leads_mod

    source = "Yandex" if config.YANDEX_API_KEY else "Overpass (OSM)"
    await message.answer(f"Lead test boshlandi — manba: {source}...")

    test_pairs = [
        ("klinika", "Toshkent"),
        ("restoran", "Toshkent"),
        ("go'zallik salon", "Toshkent"),
        ("klinika", "Samarqand"),
        ("restoran", "Samarqand"),
    ]

    total = 0
    lines = []
    for cat, city in test_pairs:
        try:
            results = await leads_mod.fetch_leads(cat, city, count=5)
            if results:
                lines.append(f"\n*{cat} / {city}* — {len(results)} ta:")
                for r in results[:3]:
                    lines.append(f"  • {r['name']}: {r['phone']}")
                total += len(results)
        except Exception as e:
            lines.append(f"\n*{cat} / {city}* — xato: {e}")

    if total == 0:
        await message.answer(
            f"{source} hech narsa qaytarmadi.\n"
            "YANDEX_API_KEY Render ga qo'shilganini tekshiring."
        )
    else:
        await message.answer(
            f"Jami *{total}* ta mobil raqamli lead ({source}):\n" + "\n".join(lines),
            parse_mode="Markdown"
        )


@dp.message(Command("report"))
async def on_report(message: Message):
    if not is_developer(message.chat.id):
        return
    await message.answer("Hisobot tayyorlanmoqda...")
    try:
        text = await reports.build_evening_summary()
        await message.answer(text, parse_mode="Markdown")
    except Exception as e:
        await message.answer(f"Xato: {e}")


@dp.message(Command("leads"))
async def on_leads(message: Message):
    if not is_developer(message.chat.id):
        return
    import database as db_mod
    stats = db_mod.get_leads_stats_today()
    total_new = db_mod.count_new_leads()
    lines = [
        "<b>LEADS HOLATI</b>\n",
        f"Navbatda: {total_new} ta yangi lead\n",
        "<b>Bugun:</b>",
        f"  Yuborildi: {stats['sent']} ta",
        f"  Javob berdi: {stats['replied']} ta",
        f"  Javob bermadi: {stats['no_reply']} ta",
    ]
    if stats["failed"]:
        lines.append(f"  Xato: {stats['failed']} ta")
    lines += [
        "",
        "Keyingi outreach: 10:00 va 17:00",
    ]
    if not config.TWOGIS_API_KEY:
        lines.append("\nTWOGIS_API_KEY sozlanmagan — .env ga qo'shing")
    await message.answer("\n".join(lines), parse_mode="HTML")


@dp.message(Command("help"))
async def on_help(message: Message):
    if not is_developer(message.chat.id):
        return
    await message.answer(
        "📋 BUYRUQLAR:\n\n"
        "/status — tizim holati\n"
        "/clients — mijozlar ro'yxati\n"
        "/projects — loyihalar ro'yxati\n"
        "/leads — outreach statistikasi\n"
        "/help — shu ro'yxat\n\n"
        "📤 MIJOZGA YOZISH:\n"
        "@username yoki +998XXXXXXXXX yuboring\n\n"
        "🔕 DEEP WORK:\n"
        "'deep work on' — mijoz javoblari tasdiqdan o'tadi\n"
        "'deep work off' — to'g'ridan-to'g'ri javob"
    )


@dp.message(F.voice | F.audio)
async def on_voice(message: Message):
    if not transcribe.enabled():
        await message.answer("Ovozli xabarni hozir o'qiy olmadim — matn ko'rinishida yuboring.")
        return
    voice = message.voice or message.audio
    tmp = os.path.join(tempfile.gettempdir(), f"{voice.file_id}.ogg")
    try:
        await bot.download(voice, destination=tmp)
        text = await transcribe.transcribe(tmp)
    except Exception as e:
        log.exception("Transkripsiya xatosi")
        await message.answer(f"Ovozni o'qishda muammo bo'ldi: {e}")
        return
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    await _handle_text(message, text)


@dp.message(F.text)
async def on_text(message: Message):
    await _handle_text(message, message.text)


async def _handle_text(message: Message, text: str):
    chat_id = message.chat.id

    if is_developer(chat_id):
        # Outreach jarayonida nom kiritish kutilayotgan bo'lsa
        if outreach.waiting_for_name(chat_id):
            resp_text, kb = await outreach.handle_name_input(text.strip(), chat_id)
            if resp_text:
                await message.answer(resp_text, reply_markup=kb, parse_mode="Markdown")
                return

        # Telefon raqamidagi bo'shliqlarni olib tashlab tekshirish
        # "+998 90 996 04 56" → "+998909960456"
        normalized = re.sub(r'(\+[\d ]{9,20})', lambda m: m.group(0).replace(' ', ''), text.strip())
        m = _CONTACT_RE.match(normalized)
        if m:
            identifier = m.group(1)
            msg_text, kb = await outreach.start(identifier, chat_id)
            await message.answer(msg_text, reply_markup=kb, parse_mode="Markdown")
            return

        # Dasturchi uchun AI javob bermaydi — faqat buyruqlar va outreach ishlaydi
        return

    # Mijoz yo'li — LLM
    try:
        visible, action = await _run_llm(chat_id, text)
    except Exception as e:
        log.exception("LLM xatosi: %s", e)
        await message.answer("Hozir javob bera olmadim, biroz kutib qaytadan yuboring.")
        return

    reply_to_sender = visible
    if action:
        reply_to_sender = await _apply_action(action, message, visible)

    if reply_to_sender:
        await message.answer(reply_to_sender)


@dp.callback_query(F.data.startswith("oq:"))
async def on_outreach_cb(cb: CallbackQuery):
    """Outreach savolnomasi callback."""
    if not is_developer(cb.from_user.id):
        await cb.answer()
        return
    text, kb, done = await outreach.handle_callback(cb.data, cb.from_user.id)
    await cb.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await cb.answer()


@dp.callback_query(F.data.startswith("uappr:"))
async def on_userbot_approval(cb: CallbackQuery):
    """Deep Work: userbot orqali yuborilgan javobni tasdiqlash."""
    _, approval_id, decision = cb.data.split(":")
    appr = db.get_approval(int(approval_id))
    if not appr or appr["status"] != "pending":
        await cb.answer("Bu so'rov allaqachon ko'rib chiqilgan.", show_alert=True)
        return
    if decision == "ok":
        await userbot.send_via_userbot(appr["client_chat"], appr["draft"])
        db.set_approval_status(int(approval_id), "sent")
        await cb.message.edit_text(cb.message.text + "\n\n✅ Mijozga yuborildi (userbot).")
    else:
        db.set_approval_status(int(approval_id), "rejected")
        await cb.message.edit_text(cb.message.text + "\n\n❌ Bekor qilindi.")
    await cb.answer()


@dp.callback_query(F.data.startswith("pay:"))
async def on_payment_approval(cb: CallbackQuery):
    """To'lov screenshoti tasdiqlash."""
    _, screenshot_id, decision = cb.data.split(":")
    sc = db.get_payment_screenshot(int(screenshot_id))
    if not sc or sc["status"] != "pending":
        await cb.answer("Allaqachon ko'rib chiqilgan.", show_alert=True)
        return

    client_chat = sc["client_chat"]
    client_name = sc["client_name"] or str(client_chat)

    if decision == "ok":
        db.set_payment_screenshot_status(int(screenshot_id), "approved")
        await userbot.send_via_userbot(
            client_chat,
            "To'lovingiz tasdiqlandi. Loyiha qabul qilindi, ishni boshlaymiz."
        )
        await userbot.add_to_hamkorlar(client_chat)
        caption = (cb.message.caption or cb.message.text or "") + "\n\nTASDIQLANDI"
        try:
            await cb.message.edit_caption(caption, reply_markup=None)
        except Exception:
            await cb.message.edit_text(caption, reply_markup=None)
        await cb.answer("Tasdiqlandi!")
    else:
        db.set_payment_screenshot_status(int(screenshot_id), "rejected")
        await userbot.send_via_userbot(
            client_chat,
            "Kechirasiz, screenshot aniq ko'rinmadi. To'liq ekran rasmini qaytadan yuboring."
        )
        caption = (cb.message.caption or cb.message.text or "") + "\n\nQAYTARILDI"
        try:
            await cb.message.edit_caption(caption, reply_markup=None)
        except Exception:
            await cb.message.edit_text(caption, reply_markup=None)
        await cb.answer("Qaytarildi.")


@dp.callback_query(F.data.startswith("appr:"))
async def on_approval(cb: CallbackQuery):
    _, approval_id, decision = cb.data.split(":")
    appr = db.get_approval(int(approval_id))
    if not appr or appr["status"] != "pending":
        await cb.answer("Bu so'rov allaqachon ko'rib chiqilgan.", show_alert=True)
        return
    if decision == "ok":
        await bot.send_message(appr["client_chat"], appr["draft"])
        db.set_approval_status(int(approval_id), "sent")
        await cb.message.edit_text(cb.message.text + "\n\n✅ Mijozga yuborildi.")
    else:
        db.set_approval_status(int(approval_id), "rejected")
        await cb.message.edit_text(cb.message.text + "\n\n❌ Bekor qilindi.")
    await cb.answer()
