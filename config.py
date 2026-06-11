"""Konfiguratsiya: barcha sozlamalar .env faylidan o'qiladi."""
import os
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()


def _req(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Majburiy sozlama yo'q: {name} (.env faylga qo'shing)")
    return val


# --- Telegram ---
TELEGRAM_BOT_TOKEN = _req("TELEGRAM_BOT_TOKEN")

# Dasturchining (sizning) shaxsiy Telegram chat ID. Hisobotlar va
# tasdiqlash so'rovlari shu yerga keladi. Botga yozsangiz, log'da ID chiqadi.
DEVELOPER_CHAT_ID = int(os.getenv("DEVELOPER_CHAT_ID", "0"))

# --- Groq LLM ---
GROQ_API_KEY = _req("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "600"))

# --- Telegram Userbot (my.telegram.org dan olinadi) ---
TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID") or "0")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
USERBOT_SESSION = os.getenv("USERBOT_SESSION", "userbot_session")

# --- To'lov ---
CARD_NUMBER = os.getenv("CARD_NUMBER", "")
HAMKORLAR_GROUP_ID = int(os.getenv("HAMKORLAR_GROUP_ID") or "0")
PORTFOLIO_LINK = os.getenv("PORTFOLIO_LINK", "")

# --- Ovozli xabar (Whisper, ixtiyoriy) ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-1")

# --- GitHub ---
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "")   # masalan: rawdovs
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")         # private repo uchun (ixtiyoriy)
WEBHOOK_HOST = "0.0.0.0"
# Render $PORT beradi, yo'q bo'lsa 8080 (local)
WEBHOOK_PORT = int(os.getenv("PORT") or os.getenv("WEBHOOK_PORT", "8080"))

# --- Vaqt va jadval ---
TIMEZONE = ZoneInfo(os.getenv("TIMEZONE", "Asia/Tashkent"))
MORNING_HOUR = int(os.getenv("MORNING_HOUR", "9"))    # 09:00 analitika
EVENING_HOUR = int(os.getenv("EVENING_HOUR", "21"))   # 21:00 progress so'rovi

# --- Biznes qoidalar ---
ADVANCE_PERCENT = int(os.getenv("ADVANCE_PERCENT", "50"))  # avans foizi
DB_PATH = os.getenv("DB_PATH", "assistant.db")

# --- Avtomatik outreach (2GIS leads) ---
TWOGIS_API_KEY = os.getenv("TWOGIS_API_KEY", "")   # developer.2gis.com dan olinadi
OUTREACH_DAILY = int(os.getenv("OUTREACH_DAILY", "10"))  # har bir seans uchun (10:00 va 17:00)
