"""GitHub Events API — bugungi commitlarni avtomatik o'qiydi."""
import logging
from datetime import datetime

import aiohttp

import config

log = logging.getLogger(__name__)


async def fetch_today_commits() -> list[dict]:
    """Bugun qilingan barcha commitlarni qaytaradi.

    Qaytaradi: [{"repo": "sihat-bot", "message": "fix: ...", "sha": "abc123"}, ...]
    """
    if not config.GITHUB_USERNAME:
        return []

    today = datetime.now(config.TIMEZONE).date().isoformat()

    headers = {"Accept": "application/vnd.github+json"}
    if config.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {config.GITHUB_TOKEN}"

    url = f"https://api.github.com/users/{config.GITHUB_USERNAME}/events"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=headers,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status == 403:
                    log.warning("GitHub rate limit yetdi yoki token noto'g'ri")
                    return []
                if resp.status != 200:
                    log.warning("GitHub API %d", resp.status)
                    return []
                events = await resp.json()
    except Exception as e:
        log.warning("GitHub API xatosi: %s", e)
        return []

    commits = []
    for event in events:
        if event.get("type") != "PushEvent":
            continue
        # created_at = "2025-06-11T15:30:00Z" — UTC, lekin sana solishtirish uchun yetarli
        event_date = event.get("created_at", "")[:10]
        if event_date != today:
            continue
        repo_full = event.get("repo", {}).get("name", "")
        repo_name = repo_full.split("/")[-1]
        for commit in event.get("payload", {}).get("commits", []):
            msg = commit.get("message", "").strip().split("\n")[0]
            sha = commit.get("sha", "")[:7]
            if msg and not msg.startswith("Merge"):
                commits.append({"repo": repo_name, "message": msg, "sha": sha})

    log.info("GitHub: bugun %d ta commit topildi", len(commits))
    return commits
