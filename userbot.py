"""Telethon userbot: dasturchining Telegram akkauntini to'liq boshqarish."""
import asyncio
import logging
import random
import time
from collections import defaultdict, deque
from typing import Optional

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import User

import config
import database as db
import llm

log = logging.getLogger(__name__)

_client: Optional[TelegramClient] = None
_history: dict[int, deque] = defaultdict(lambda: deque(maxlen=16))
_chat_locks: dict[int, asyncio.Lock] = {}
_error_cooldown: dict[int, float] = {}
_dev_notify_times: deque = deque(maxlen=10)
_startup_ts: float = 0

FOLLOW_UP_MESSAGES = [
    "Salom! Avvalgi xabarimga javob kelmadi. Telegram bot loyihasi bo'yicha qiziqish bormi?",
    "Yana bir marta so'ramoqchi edim — Telegram bot yoki web loyiha kerak bo'lsa, yordam bera olaman.",
]


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _get_name(sender) -> str:
    return " ".join(filter(None, [
        getattr(sender, "first_name", None),
        getattr(sender, "last_name", None)
    ])) or str(getattr(sender, "id", "?"))


def _build_context(sender_id: int = None) -> str:
    parts = []
    if sender_id:
        client_proj = db.find_project_by_client_chat(sender_id)
        if client_proj:
            parts.append(
                f"BU MIJOZNING LOYIHASI: '{client_proj['name']}' — "
                f"{client_proj['progress']:g}% tayyor, {client_proj['duration_days']} kunlik. "
                "Bu MAVJUD MIJOZ — sotuv strategiyasini ISHLATMA, 'biznesingiz nima?' DEMA."
            )
        else:
            parts.append("Hozir MIJOZ bilan gaplashyapsan (sotuv rejimi). Dasturchi nomidan gapir.")
    else:
        parts.append("Hozir MIJOZ bilan gaplashyapsan (sotuv rejimi). Dasturchi nomidan gapir.")
    projs = db.active_projects()
    if projs:
        lst = "; ".join(f"{p['name']} ({p['progress']:g}%)" for p in projs)
        parts.append(f"Barcha faol loyihalar: {lst}.")
    if config.CARD_NUMBER:
        parts.append(f"To'lov kartasi: {config.CARD_NUMBER}")
    if config.PORTFOLIO_LINK:
        parts.append(f"PORTFOLIO_LINK: {config.PORTFOLIO_LINK}")
    return "\n".join(parts)


async def _notify_developer(text: str, silent: bool = False, **kwargs) -> None:
    if not config.DEVELOPER_CHAT_ID:
        return
    now = time.time()
    while _dev_notify_times and now - _dev_notify_times[0] > 60:
        _dev_notify_times.popleft()
    if len(_dev_notify_times) >= 10:
        return
    _dev_notify_times.append(now)
    from core import bot as tg_bot
    try:
        await tg_bot.send_message(config.DEVELOPER_CHAT_ID, text,
                                  disable_notification=silent, **kwargs)
    except Exception as e:
        log.error("Dev notify xatosi: %s", e)


# ─── Init ────────────────────────────────────────────────────────────────────

async def _connect_client() -> bool:
    """Clientni ulab, authorized ekanini tekshiradi. True = muvaffaqiyatli."""
    global _client, _startup_ts
    try:
        if _client and _client.is_connected():
            return True
        if _client:
            await _client.disconnect()

        session_val = config.USERBOT_SESSION
        session = StringSession(session_val) if len(session_val) > 50 else session_val
        _client = TelegramClient(session, config.TELEGRAM_API_ID, config.TELEGRAM_API_HASH)

        await _client.connect()
        if not await _client.is_user_authorized():
            log.error("Userbot session yaroqsiz. USERBOT_SESSION ni yangilang.")
            _client = None
            return False
        me = await _client.get_me()
        _startup_ts = time.time()
        log.info("Userbot ulandi: @%s (id=%s)", me.username, me.id)
        return True
    except Exception as e:
        log.error("Userbot ulanishda xato: %s", e)
        _client = None
        return False


async def init() -> None:
    global _client
    if not config.TELEGRAM_API_ID or not config.TELEGRAM_API_HASH:
        log.warning("TELEGRAM_API_ID yoki TELEGRAM_API_HASH yo'q — userbot o'chirilgan.")
        return

    ok = await _connect_client()
    if not ok:
        return

    @_client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
    async def on_incoming(event):
        if event.message.date.timestamp() < _startup_ts - 10:
            return

        sender_id: int = event.sender_id
        sender: User = await event.get_sender()

        if getattr(sender, "bot", False):
            return

        # Screenshot (to'lov rasmi)
        is_photo = bool(event.message.photo)
        is_img_doc = (event.message.document and
                      getattr(event.message.document, "mime_type", "").startswith("image/"))
        if is_photo or is_img_doc:
            if sender_id not in _chat_locks:
                _chat_locks[sender_id] = asyncio.Lock()
            async with _chat_locks[sender_id]:
                await _handle_screenshot(event, sender_id, sender)
            return

        text: str = (event.message.text or "").strip()
        if not text:
            await _client.send_message(sender_id,
                "Kechirasiz, faqat matnli xabarlarni o'qiy olaman. Savolingizni yozing.")
            return

        if sender_id not in _chat_locks:
            _chat_locks[sender_id] = asyncio.Lock()
        async with _chat_locks[sender_id]:
            await _process_message(event, sender_id, text, sender)


# ─── Screenshot handling ─────────────────────────────────────────────────────

async def _handle_screenshot(event, sender_id: int, sender: User) -> None:
    name = _get_name(sender)
    log.info("Userbot: %s dan to'lov screenshoti keldi", name)

    try:
        photo_bytes = await _client.download_media(event.message, bytes)
    except Exception as e:
        log.exception("Screenshot yuklab olishda xato")
        return

    screenshot_id = db.create_payment_screenshot(sender_id, name)

    from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
    from core import bot as tg_bot

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ To'lov tasdiqlandi", callback_data=f"pay:{screenshot_id}:ok"),
        InlineKeyboardButton(text="❌ Qaytadan so'rash", callback_data=f"pay:{screenshot_id}:no"),
    ]])

    photo_file = BufferedInputFile(photo_bytes, filename="payment.jpg")
    try:
        await tg_bot.send_photo(
            config.DEVELOPER_CHAT_ID,
            photo=photo_file,
            caption=f"To'lov screenshoti\n{name} ({sender_id})",
            reply_markup=kb,
        )
    except Exception as e:
        log.error("Screenshotni botga yuborishda xato: %s", e)
        return

    await _client.send_message(
        sender_id,
        "Screenshot qabul qilindi. Tekshirib ko'raman, biroz kutib turing."
    )


# ─── Message processing ───────────────────────────────────────────────────────

async def _process_message(event, sender_id: int, text: str, sender: User = None) -> None:
    if sender is None:
        sender = await event.get_sender()

    name = _get_name(sender)
    username = getattr(sender, "username", None)

    db.upsert_userbot_chat(sender_id, name=name, username=username, last_message=text[:200])
    db.resolve_follow_up(sender_id)
    db.mark_lead_replied_by_chat_id(sender_id)
    log.info("Userbot <- %s (%s): %s", name, sender_id, text[:80])

    hist = _history[sender_id]
    is_new_session = len(hist) == 0

    # Birinchi xabar — mavjud loyiha borligini tekshir
    if is_new_session:
        existing_proj = db.find_project_by_client_chat(sender_id)
        if existing_proj:
            # Mavjud mijoz — loyiha haqida biladi, sotuv emas yordam rejimi
            reply = f"Salom! Loyihangiz haqida savolingiz bormi?"
        else:
            reply = "Assalomu alaykum! Labbay, nima xizmat?"
        await asyncio.sleep(random.uniform(1.5, 3.0))
        await _client.send_message(sender_id, reply)

        hist.append({"role": "user", "content": text})
        hist.append({"role": "assistant", "content": reply})
        return

    # Mavjud sessiya — AI javob beradi
    hist.append({"role": "user", "content": text})

    try:
        raw = await llm.ask(list(hist), extra_system=_build_context(sender_id))
        visible, action = llm.extract_action(raw)
        hist.append({"role": "assistant", "content": raw})
    except Exception as e:
        log.exception("LLM xatosi (userbot, chat=%s)", sender_id)
        now = time.time()
        if now - _error_cooldown.get(sender_id, 0) > 60:
            _error_cooldown[sender_id] = now
            await _notify_developer(f"LLM xatosi — {name} xabariga javob berilmadi\n`{e}`")
        return

    # Inson kabi kechikish: 3–7 soniya, uzun javob bo'lsa biroz ko'proq
    base_delay = random.uniform(3.0, 6.0)
    length_bonus = min(len(visible) / 300, 3.0)  # har 300 harf uchun +1s, max +3s
    await asyncio.sleep(base_delay + length_bonus)

    if db.deep_work_on() and action and action.get("action") == "PENDING_APPROVAL":
        await _request_approval(sender_id, name, visible)
    else:
        async with _client.action(sender_id, "typing"):
            await asyncio.sleep(random.uniform(1.0, 2.5))
        await _client.send_message(sender_id, visible)
        log.info("Userbot -> %s: %s", name, visible[:80])

    if action:
        await _handle_action(action, sender_id, name, visible)


# ─── Actions ─────────────────────────────────────────────────────────────────

async def _handle_action(action: dict, sender_id: int, name: str, visible: str) -> None:
    kind = action.get("action")

    if kind == "CLIENT_REJECTED":
        _history[sender_id].clear()
        db.upsert_userbot_chat(sender_id, status="rejected")
        db.resolve_follow_up(sender_id)
        log.info("Mijoz rad etdi, tarix tozalandi: %s (%s)", name, sender_id)

    elif kind == "CREATE_PROJECT":
        import actions as act
        summary = act.create_project(action, client_chat=sender_id, client_label=name)
        row = db._conn.execute(
            "SELECT username FROM userbot_chats WHERE chat_id=?", (sender_id,)
        ).fetchone()
        uname_str = f"@{row['username']}" if row and row["username"] else str(sender_id)
        await _notify_developer(
            f"ZAKAZ OLINDI\n"
            f"Mijoz: {name} ({uname_str})\n\n"
            f"{summary}"
        )

    elif kind == "UPDATE_PROGRESS":
        import actions as act
        act.update_progress(action, source="userbot")

    elif kind == "ESCALATE":
        db.upsert_userbot_chat(sender_id, status="escalated")
        log.info("Eskalatsiya: %s (%s) — %s", name, sender_id, action.get("reason", "—"))

    elif kind == "REQUEST_PAYMENT":
        log.info("To'lov kelishildi: %s (%s)", name, sender_id)


async def _request_approval(sender_id: int, name: str, visible: str) -> None:
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from core import bot as tg_bot
    approval_id = db.create_approval(sender_id, visible)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Yuborish", callback_data=f"uappr:{approval_id}:ok"),
        InlineKeyboardButton(text="Bekor", callback_data=f"uappr:{approval_id}:no"),
    ]])
    await tg_bot.send_message(
        config.DEVELOPER_CHAT_ID,
        f"{name} uchun javob:\n\n{visible}",
        reply_markup=kb,
    )


# ─── Follow-up ───────────────────────────────────────────────────────────────

async def run_follow_ups() -> None:
    """Scheduler tomonidan chaqiriladi: javob bermagan kontaktlarga takroriy xabar."""
    if not _client or not _client.is_connected():
        return

    from datetime import datetime, timezone
    now_utc = datetime.now(timezone.utc)

    # 1. 3 urinishdan o'tgan, 3+ kun kutilgan follow-up larni arxivlash
    max_reached = db._conn.execute(
        "SELECT * FROM follow_ups WHERE status='max_attempts'"
    ).fetchall()
    for fu in max_reached:
        last = fu["last_attempt"]
        if not last:
            continue
        last_dt = datetime.fromisoformat(last).replace(tzinfo=timezone.utc)
        days_since = (now_utc - last_dt).days
        if days_since >= 3:
            db._conn.execute(
                "UPDATE follow_ups SET status='archived' WHERE id=?", (fu["id"],)
            )
            db._conn.commit()
            _history[fu["chat_id"]].clear()
            db.upsert_userbot_chat(fu["chat_id"], status="archived")
            await _notify_developer(
                f"Arxivlandi\n{fu['name']} — 6 kun ichida javob bermadi, o'chirildi."
            )
            log.info("Follow-up arxivlandi: %s", fu["name"])

    # 2. Faol follow-up larga xabar yuborish (3 ta urinish)
    pending = db.get_pending_follow_ups()
    for fu in pending:
        chat_id = fu["chat_id"]
        if not chat_id:
            continue
        attempts = fu["attempts"]
        msg_idx = min(attempts - 1, len(FOLLOW_UP_MESSAGES) - 1)
        msg = FOLLOW_UP_MESSAGES[msg_idx]
        try:
            await _client.send_message(chat_id, msg)
            new_attempts = db.increment_follow_up(fu["id"])
            log.info("Follow-up yuborildi: %s (urinish %d)", fu["name"], new_attempts)
            if new_attempts >= 3:
                # 3 urinish tugadi — "max_attempts" holatiga o'tkazish
                db._conn.execute(
                    "UPDATE follow_ups SET status='max_attempts' WHERE id=?", (fu["id"],)
                )
                db._conn.commit()
                await _notify_developer(
                    f"3 kun javob yo'q\n{fu['name']} — yana 3 kundan keyin arxivlanadi."
                )
        except Exception as e:
            log.warning("Follow-up yuborishda xato (%s): %s", fu["name"], e)
        await asyncio.sleep(2)


# ─── Hamkorlar papkasi ────────────────────────────────────────────────────────

HAMKORLAR_FOLDER_ID = 2  # Telegram papka ID


async def add_to_hamkorlar(client_id: int) -> None:
    """Mijozni 'Hamkorlar' papkasiga qo'shadi."""
    if not _client:
        return
    try:
        from telethon.tl.functions.messages import GetDialogFiltersRequest, UpdateDialogFilterRequest
        from telethon.tl.types import DialogFilter, InputPeerUser

        # Joriy papka ma'lumotlarini olish
        result = await _client(GetDialogFiltersRequest())
        target = None
        for f in result.filters:
            if getattr(f, "id", None) == HAMKORLAR_FOLDER_ID:
                target = f
                break

        if target is None:
            log.warning("Hamkorlar papkasi topilmadi (ID=%s)", HAMKORLAR_FOLDER_ID)
            return

        # Mijoz entity olish
        entity = await _client.get_entity(client_id)
        peer = await _client.get_input_entity(entity)

        # Agar allaqachon qo'shilgan bo'lsa — o'tkazib yuboramiz
        existing_ids = {getattr(p, "user_id", None) or getattr(p, "chat_id", None)
                        for p in target.include_peers}
        if client_id in existing_ids:
            log.info("Mijoz allaqachon Hamkorlar papkasida: %s", client_id)
            return

        target.include_peers.append(peer)
        await _client(UpdateDialogFilterRequest(id=HAMKORLAR_FOLDER_ID, filter=target))
        log.info("Mijoz Hamkorlar papkasiga qo'shildi: %s", client_id)
    except Exception as e:
        log.warning("Hamkorlar papkasiga qo'shishda xato: %s", e)


# ─── Public API ──────────────────────────────────────────────────────────────

async def _resolve_entity(identifier: str):
    """Identifier (@username yoki +telefon) bo'yicha Telegram entity qaytaradi.
    Telefon raqam kontaktlarda bo'lmasa, ImportContactsRequest orqali topadi.
    """
    try:
        return await _client.get_entity(identifier)
    except (ValueError, Exception) as first_err:
        if not identifier.startswith('+'):
            raise

        from telethon.tl.functions.contacts import ImportContactsRequest
        from telethon.tl.types import InputPhoneContact

        result = await _client(ImportContactsRequest([
            InputPhoneContact(client_id=0, phone=identifier, first_name="Temp", last_name="")
        ]))
        if result.users:
            return result.users[0]
        raise first_err


async def start_conversation(identifier: str, first_message: str = None) -> tuple[str, int | None]:
    """Yangi kontaktga birinchi xabar yuboradi.

    Qaytaradi: (natija_matni, telegram_chat_id)
    """
    if not _client or not _client.is_connected():
        log.warning("Userbot uzilgan, qayta ulanmoqda...")
        ok = await _connect_client()
        if not ok:
            return "Userbot ulanmadi. USERBOT_SESSION ni tekshiring.", None
    try:
        entity = await _resolve_entity(identifier)
        chat_id: int = entity.id
        name = _get_name(entity)
        username = getattr(entity, "username", None)

        if not first_message:
            first_message = (
                "Assalomu alaykum! Telegram bot va web loyihalar bo'yicha "
                "gaplashmoqchi edim. Bir daqiqangiz bormi?"
            )

        await _client.send_message(entity, first_message)
        _history[chat_id].append({"role": "assistant", "content": first_message})
        db.upsert_userbot_chat(chat_id, name=name, username=username,
                               last_message=first_message[:200])
        db.create_follow_up(chat_id, identifier, name)

        uname_str = f"@{username}" if username else identifier
        log.info("Userbot -> yangi kontakt %s (%s)", name, uname_str)
        return f"✅ {name} ({uname_str}) ga xabar yuborildi.", chat_id
    except Exception as e:
        log.exception("start_conversation xatosi")
        if "Cannot find any entity" in str(e):
            return f"❌ {identifier} — Telegram akkaunt topilmadi.", None
        return f"❌ Xabar yuborishda xato: {e}", None


async def send_via_userbot(client_chat: int, text: str) -> None:
    if not _client or not _client.is_connected():
        await _connect_client()
    if _client and _client.is_connected():
        await _client.send_message(client_chat, text)
        _history[client_chat].append({"role": "assistant", "content": text})


def is_running() -> bool:
    return _client is not None and _client.is_connected()


async def disconnect() -> None:
    if _client:
        await _client.disconnect()
