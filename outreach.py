"""Mijoz jalb qilish jarayoni.

Dasturchi @username yoki +telefon yuborganida:
  1. Biznes turi (keyboard)
  2. Sub-tur (keyboard)
  3. Biznes nomi (matn)
  4. Asosiy maqsad (keyboard)
  5. Tayyor xabar preview + tasdiqlash
"""
import logging
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

import userbot

log = logging.getLogger(__name__)

# ─── State ────────────────────────────────────────────────────────────────────
_state: dict[int, dict] = {}  # dev_chat_id -> state dict


def active(dev_chat_id: int) -> bool:
    return dev_chat_id in _state


def waiting_for_name(dev_chat_id: int) -> bool:
    s = _state.get(dev_chat_id)
    return s is not None and s["step"] == "biz_name"


def clear(dev_chat_id: int) -> None:
    _state.pop(dev_chat_id, None)


# ─── Keyboards ────────────────────────────────────────────────────────────────
def _kb(*rows):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, callback_data=d) for t, d in row]
        for row in rows
    ])


BIZ_TYPE_KB = _kb(
    [("Restoran / Kafe", "oq:type:restaurant"), ("Dorixona", "oq:type:pharmacy")],
    [("Klinika / Shifokor", "oq:type:clinic"), ("Boshqa biznes", "oq:type:other")],
)

SUB_TYPE_KB = {
    "restaurant": _kb(
        [("Fast-food", "oq:sub:fastfood"), ("Restoran", "oq:sub:restaurant")],
        [("Kafe", "oq:sub:cafe"), ("Qandolat / Bakery", "oq:sub:bakery")],
    ),
    "pharmacy": _kb(
        [("Oddiy dorixona", "oq:sub:pharmacy"), ("Apteka zanjiri", "oq:sub:chain")],
    ),
    "clinic": _kb(
        [("Umumiy klinika", "oq:sub:clinic"), ("Stomatologiya", "oq:sub:dental")],
        [("Go'zallik salon", "oq:sub:beauty"), ("Fitness / Sport", "oq:sub:fitness")],
    ),
    "other": _kb(
        [("Do'kon / Market", "oq:sub:shop"), ("Hotel / Mehmonxona", "oq:sub:hotel")],
        [("Ta'lim / Kurs", "oq:sub:education"), ("Boshqa", "oq:sub:other")],
    ),
}

GOAL_KB = _kb(
    [("Buyurtma / Delivery", "oq:goal:orders"), ("Navbat / Rezerv", "oq:goal:booking")],
    [("Mijozlarga xabar", "oq:goal:broadcast"), ("Hammasini", "oq:goal:all")],
)

CONFIRM_KB = _kb(
    [("Yuborish", "oq:confirm:send"), ("Qayta yozish", "oq:confirm:rewrite")],
    [("Bekor", "oq:confirm:cancel")],
)


# ─── Message generator ────────────────────────────────────────────────────────
def _gen_message(s: dict) -> str:
    name = s["biz_name"]
    sub = s["sub_type"]
    goal = s["goal"]
    biz_type = s["biz_type"]

    goal_phrase = {
        "orders":    "buyurtmalarni Telegram bot orqali qabul qilish",
        "booking":   "onlayn navbat va rezerv tizimi",
        "broadcast": "mijozlarga avtomatik xabar yuborish",
        "all":       "savdoni Telegram bot orqali avtomatlashtirish",
    }.get(goal, "Telegram bot")

    if biz_type == "restaurant":
        entity = {
            "fastfood": "fast-food", "restaurant": "restoran",
            "cafe": "kafe", "bakery": "qandolat",
        }.get(sub, "biznes")
        return (
            f"Assalomu alaykum, {name}!\n\n"
            f"{entity.capitalize()}lar uchun {goal_phrase} tizimini ishlab chiqaman. "
            f"Operatorlarsiz, to'liq avtomatik.\n\n"
            f"Qiziq bo'lsa, gaplashib ko'rsak bo'ladimi?"
        )

    elif biz_type == "pharmacy":
        return (
            f"Assalomu alaykum, {name}!\n\n"
            f"Dorixonalar uchun {goal_phrase} tizimini ishlab chiqaman. "
            f"Mijozlar bot orqali so'raydi, telefon kerak emas.\n\n"
            f"Qiziq bo'lsa, gaplashib ko'rsak bo'ladimi?"
        )

    elif biz_type == "clinic":
        entity = {
            "clinic": "klinika", "dental": "stomatologiya",
            "beauty": "go'zallik salon", "fitness": "fitness markaz",
        }.get(sub, "tibbiyot muassasasi")
        return (
            f"Assalomu alaykum, {name}!\n\n"
            f"{entity.capitalize()}lar uchun {goal_phrase} tizimini ishlab chiqaman. "
            f"Bemorlar telefon qilmasdan, bot orqali navbat oladi.\n\n"
            f"Qiziq bo'lsa, gaplashib ko'rsak bo'ladimi?"
        )

    else:
        entity = {
            "shop": "do'kon", "hotel": "mehmonxona",
            "education": "ta'lim markaz", "other": "biznes",
        }.get(sub, "biznes")
        return (
            f"Assalomu alaykum, {name}!\n\n"
            f"{entity.capitalize()}lar uchun {goal_phrase} tizimini ishlab chiqaman. "
            f"Mijozlar bilan ishlash to'liq avtomatik bo'ladi.\n\n"
            f"Qiziq bo'lsa, gaplashib ko'rsak bo'ladimi?"
        )


# ─── Step labels ──────────────────────────────────────────────────────────────
_TYPE_LABEL = {
    "restaurant": "Restoran/Kafe",
    "pharmacy": "Dorixona",
    "clinic": "Klinika",
    "other": "Boshqa",
}
_SUB_LABEL = {
    "fastfood": "Fast-food", "restaurant": "Restoran", "cafe": "Kafe", "bakery": "Qandolat",
    "pharmacy": "Dorixona", "chain": "Apteka zanjiri",
    "clinic": "Klinika", "dental": "Stomatologiya", "beauty": "Go'zallik salon", "fitness": "Fitness",
    "shop": "Do'kon", "hotel": "Hotel", "education": "Ta'lim", "other": "Boshqa",
}
_GOAL_LABEL = {
    "orders": "Buyurtma/Delivery",
    "booking": "Navbat/Rezerv",
    "broadcast": "Mass xabar",
    "all": "Hammasi",
}


def _progress(s: dict) -> str:
    lines = [f"*Xabar tayyorlanmoqda*\nKimga: `{s['identifier']}`"]
    if s.get("biz_type"):
        lines.append(f"Tur: {_TYPE_LABEL.get(s['biz_type'], s['biz_type'])}")
    if s.get("sub_type"):
        lines.append(f"Kichik tur: {_SUB_LABEL.get(s['sub_type'], s['sub_type'])}")
    if s.get("biz_name"):
        lines.append(f"Nomi: {s['biz_name']}")
    if s.get("goal"):
        lines.append(f"Maqsad: {_GOAL_LABEL.get(s['goal'], s['goal'])}")
    return "\n".join(lines)


# ─── Public API ───────────────────────────────────────────────────────────────
async def start(identifier: str, dev_chat_id: int) -> tuple[str, InlineKeyboardMarkup]:
    _state[dev_chat_id] = {
        "identifier": identifier,
        "step": "biz_type",
        "biz_type": None, "sub_type": None, "biz_name": None,
        "goal": None, "draft": None,
    }
    text = f"*Xabar tayyorlanmoqda*\nKimga: `{identifier}`\n\n*1/4 — Biznes turi:*"
    return text, BIZ_TYPE_KB


async def handle_callback(data: str, dev_chat_id: int) -> tuple[str, object, bool]:
    s = _state.get(dev_chat_id)
    if not s:
        return "Jarayon topilmadi. @username qaytadan yuboring.", None, True

    _, step, value = data.split(":", 2)

    if step == "type":
        s["biz_type"] = value
        s["step"] = "sub_type"
        text = f"{_progress(s)}\n\n*2/4 — Kichik tur:*"
        return text, SUB_TYPE_KB[value], False

    if step == "sub":
        s["sub_type"] = value
        s["step"] = "biz_name"
        text = f"{_progress(s)}\n\n*3/4 — Biznes nomini yozing:*"
        return text, None, False

    if step == "goal":
        s["goal"] = value
        s["step"] = "confirm"
        draft = _gen_message(s)
        s["draft"] = draft
        text = f"{_progress(s)}\n\n---\n\n{draft}\n\n---\n\n*Yuborishni tasdiqlang:*"
        return text, CONFIRM_KB, False

    if step == "confirm":
        if value == "cancel":
            clear(dev_chat_id)
            return "Bekor qilindi.", None, True

        if value == "rewrite":
            s["step"] = "goal"
            s["goal"] = None
            text = f"{_progress(s)}\n\n*4/4 — Asosiy maqsad:*"
            return text, GOAL_KB, False

        if value == "send":
            ident = s["identifier"]
            draft = s["draft"]
            clear(dev_chat_id)
            result = await userbot.start_conversation(ident, draft)
            return f"Yuborildi!\n\n{result}", None, True

    return "Noma'lum qadam.", None, True


async def handle_name_input(name: str, dev_chat_id: int) -> tuple[str, object]:
    s = _state.get(dev_chat_id)
    if not s or s["step"] != "biz_name":
        return None, None
    s["biz_name"] = name.strip()
    s["step"] = "goal"
    text = f"{_progress(s)}\n\n*4/4 — Asosiy maqsad:*"
    return text, GOAL_KB
