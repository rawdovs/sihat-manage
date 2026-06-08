"""GitHub webhook serveri: push hodisasida commitlarni tahlil qiladi."""
import hashlib
import hmac
import json
import logging

from aiohttp import web

import actions
import config
import database as db
import llm
from core import bot

log = logging.getLogger(__name__)


def _verify(body: bytes, signature: str) -> bool:
    if not config.GITHUB_WEBHOOK_SECRET:
        return True  # secret sozlanmagan bo'lsa, tekshirmaymiz (faqat sinov uchun)
    if not signature:
        return False
    digest = hmac.new(config.GITHUB_WEBHOOK_SECRET.encode(),
                      body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={digest}", signature)


async def _handle_push(payload: dict):
    repo = payload.get("repository", {}).get("full_name", "")
    commits = payload.get("commits", [])
    if not commits:
        return
    messages = [c.get("message", "") for c in commits]
    commit_text = "\n".join(f"- {m}" for m in messages)

    proj = db.find_project_by_repo(repo)
    prompt = (
        f"GitHub repozitoriy '{repo}' ga quyidagi commitlar keldi:\n{commit_text}\n\n"
        f"Loyiha nomi: {proj['name'] if proj else 'NOMALUM'}. "
        "Bajarilgan ishni tahlil qil va UPDATE_PROGRESS action qaytar."
    )
    try:
        raw = await llm.ask_text(prompt)
        _, action = llm.extract_action(raw)
    except Exception:
        log.exception("Commit tahlilida LLM xatosi")
        action = None

    if action and action.get("action") == "UPDATE_PROGRESS":
        if proj and not action.get("project_name"):
            action["project_name"] = proj["name"]
        summary = actions.update_progress(action, source="github")
        if config.DEVELOPER_CHAT_ID:
            await bot.send_message(
                config.DEVELOPER_CHAT_ID,
                f"🔗 GitHub commit ({repo}):\n{commit_text}\n\n{summary}",
            )
    else:
        db.add_note(f"[{repo}] {commit_text}", source="github")
        if config.DEVELOPER_CHAT_ID:
            await bot.send_message(
                config.DEVELOPER_CHAT_ID,
                f"🔗 GitHub commit keldi ({repo}), lekin progress avtomatik aniqlanmadi:\n{commit_text}",
            )


async def github_handler(request: web.Request) -> web.Response:
    body = await request.read()
    if not _verify(body, request.headers.get("X-Hub-Signature-256", "")):
        return web.Response(status=401, text="Imzo noto'g'ri")
    event = request.headers.get("X-GitHub-Event", "")
    if event == "push":
        try:
            await _handle_push(json.loads(body))
        except Exception:
            log.exception("Webhook ishlovida xato")
    return web.Response(text="ok")


async def health_handler(request: web.Request) -> web.Response:
    import userbot
    return web.json_response({
        "status": "ok",
        "userbot": userbot.is_running(),
    })


def make_app() -> web.Application:
    app = web.Application()
    app.router.add_post("/github", github_handler)
    app.router.add_get("/", lambda r: web.Response(text="ok"))
    app.router.add_get("/api/health", health_handler)
    return app
