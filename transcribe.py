"""Ovozli xabarni matnga aylantirish — OpenAI Whisper API (ixtiyoriy)."""
import config

_oai = None
if config.OPENAI_API_KEY:
    try:
        from openai import AsyncOpenAI
        _oai = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
    except Exception:
        _oai = None


def enabled() -> bool:
    return _oai is not None


async def transcribe(file_path: str) -> str:
    """Audio faylni matnga aylantiradi. Whisper sozlanmagan bo'lsa xato beradi."""
    if not _oai:
        raise RuntimeError("Whisper sozlanmagan: .env ga OPENAI_API_KEY qo'shing.")
    with open(file_path, "rb") as f:
        tr = await _oai.audio.transcriptions.create(model=config.WHISPER_MODEL, file=f)
    return tr.text.strip()
