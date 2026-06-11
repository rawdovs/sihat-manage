"""SQLite ma'lumotlar bazasi: loyihalar, to'lovlar, izohlar, sozlamalar, approval."""
import json
import sqlite3
from datetime import date, datetime
from typing import Optional

import config

_conn: Optional[sqlite3.Connection] = None


def init() -> None:
    global _conn
    _conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    _conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL,
            client_chat   INTEGER,
            client_label  TEXT,
            price_usd     REAL NOT NULL,
            duration_days INTEGER NOT NULL,
            start_date    TEXT NOT NULL,
            progress      REAL NOT NULL DEFAULT 0,
            status        TEXT NOT NULL DEFAULT 'active',
            tasks         TEXT NOT NULL DEFAULT '[]',
            github_repo   TEXT,
            created_at    TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS payments (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            kind       TEXT NOT NULL,          -- 'advance' yoki 'final'
            amount     REAL NOT NULL,
            paid       INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS notes (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id    INTEGER,
            source        TEXT NOT NULL,        -- manual / voice / github
            text          TEXT NOT NULL,
            progress_add  REAL NOT NULL DEFAULT 0,
            created_at    TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS approvals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            client_chat INTEGER NOT NULL,
            draft       TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'pending',
            created_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS userbot_chats (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id       INTEGER UNIQUE NOT NULL,
            name          TEXT,
            username      TEXT,
            message_count INTEGER NOT NULL DEFAULT 0,
            last_message  TEXT,
            status        TEXT NOT NULL DEFAULT 'active',
            first_contact TEXT NOT NULL,
            last_activity TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS payment_screenshots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            client_chat INTEGER NOT NULL,
            client_name TEXT,
            status      TEXT NOT NULL DEFAULT 'pending',
            created_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS follow_ups (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id      INTEGER,
            identifier   TEXT NOT NULL,
            name         TEXT,
            attempts     INTEGER NOT NULL DEFAULT 0,
            last_attempt TEXT,
            status       TEXT NOT NULL DEFAULT 'active',
            created_at   TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS leads (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            name             TEXT NOT NULL,
            phone            TEXT UNIQUE NOT NULL,
            category         TEXT,
            city             TEXT,
            address          TEXT,
            status           TEXT NOT NULL DEFAULT 'new',
            telegram_chat_id INTEGER,
            sent_at          TEXT,
            created_at       TEXT NOT NULL
        );
        """
    )
    _conn.commit()


def _now() -> str:
    return datetime.now(config.TIMEZONE).isoformat()


# ---------------- Settings ----------------
def set_setting(key: str, value: str) -> None:
    _conn.execute(
        "INSERT INTO settings(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    _conn.commit()


def get_setting(key: str, default: str = "") -> str:
    row = _conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def deep_work_on() -> bool:
    return get_setting("deep_work", "off") == "on"


def set_deep_work(on: bool) -> None:
    set_setting("deep_work", "on" if on else "off")


# ---------------- Projects ----------------
def create_project(name, price_usd, duration_days, tasks,
                   client_chat=None, client_label=None, github_repo=None) -> int:
    cur = _conn.execute(
        "INSERT INTO projects(name, client_chat, client_label, price_usd, "
        "duration_days, start_date, tasks, github_repo, created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (name, client_chat, client_label, float(price_usd), int(duration_days),
         date.today().isoformat(), json.dumps(tasks, ensure_ascii=False),
         github_repo, _now()),
    )
    pid = cur.lastrowid
    advance = round(float(price_usd) * config.ADVANCE_PERCENT / 100, 2)
    final = round(float(price_usd) - advance, 2)
    _conn.executemany(
        "INSERT INTO payments(project_id, kind, amount, paid, created_at) VALUES(?,?,?,?,?)",
        [(pid, "advance", advance, 0, _now()), (pid, "final", final, 0, _now())],
    )
    _conn.commit()
    return pid


def active_projects() -> list[sqlite3.Row]:
    return _conn.execute(
        "SELECT * FROM projects WHERE status = 'active' ORDER BY id"
    ).fetchall()


def find_project_by_client_chat(client_chat: int) -> Optional[sqlite3.Row]:
    """Berilgan chat_id ga tegishli oxirgi faol loyihani qaytaradi."""
    return _conn.execute(
        "SELECT * FROM projects WHERE client_chat=? AND status='active' "
        "ORDER BY id DESC LIMIT 1",
        (client_chat,),
    ).fetchone()


def find_project_by_name(name: str) -> Optional[sqlite3.Row]:
    return _conn.execute(
        "SELECT * FROM projects WHERE lower(name) = lower(?) AND status='active'",
        (name,),
    ).fetchone()


def find_project_by_repo(repo: str) -> Optional[sqlite3.Row]:
    return _conn.execute(
        "SELECT * FROM projects WHERE lower(github_repo) = lower(?) AND status='active'",
        (repo,),
    ).fetchone()


def add_progress(project_id: int, percent: float) -> float:
    row = _conn.execute("SELECT progress FROM projects WHERE id=?", (project_id,)).fetchone()
    new = min(100.0, (row["progress"] if row else 0) + percent)
    _conn.execute("UPDATE projects SET progress=? WHERE id=?", (new, project_id))
    if new >= 100:
        _conn.execute("UPDATE projects SET status='done' WHERE id=?", (project_id,))
    _conn.commit()
    return new


# ---------------- Notes ----------------
def add_note(text, source, project_id=None, progress_add=0.0) -> None:
    _conn.execute(
        "INSERT INTO notes(project_id, source, text, progress_add, created_at) VALUES(?,?,?,?,?)",
        (project_id, source, text, progress_add, _now()),
    )
    _conn.commit()


def last_note(project_id: int) -> str:
    row = _conn.execute(
        "SELECT text FROM notes WHERE project_id=? ORDER BY id DESC LIMIT 1", (project_id,)
    ).fetchone()
    return row["text"] if row else "—"


# ---------------- Finance ----------------
def finance_summary() -> tuple[float, float]:
    """Qaytaradi: (avanslar yig'indisi, kutilayotgan yakuniy to'lovlar)."""
    adv = _conn.execute(
        "SELECT COALESCE(SUM(amount),0) s FROM payments WHERE kind='advance'"
    ).fetchone()["s"]
    pend = _conn.execute(
        "SELECT COALESCE(SUM(amount),0) s FROM payments WHERE kind='final' AND paid=0"
    ).fetchone()["s"]
    return round(adv, 2), round(pend, 2)


# ---------------- Userbot chats ----------------
def upsert_userbot_chat(chat_id: int, name: str = None, username: str = None,
                        last_message: str = None, status: str = None) -> None:
    now = _now()
    existing = _conn.execute(
        "SELECT id FROM userbot_chats WHERE chat_id=?", (chat_id,)
    ).fetchone()
    if existing:
        # message_count faqat haqiqiy xabar kelganda oshadi (status update da emas)
        updates = ["last_activity = ?"]
        params = [now]
        if last_message:
            updates.append("message_count = message_count + 1")
            updates.append("last_message = ?")
            params.append(last_message)
        if status:
            updates.append("status = ?")
            params.append(status)
        params.append(chat_id)
        _conn.execute(
            f"UPDATE userbot_chats SET {', '.join(updates)} WHERE chat_id=?", params
        )
    else:
        _conn.execute(
            "INSERT INTO userbot_chats(chat_id, name, username, message_count, "
            "last_message, status, first_contact, last_activity) VALUES(?,?,?,1,?,?,?,?)",
            (chat_id, name, username, last_message, status or "active", now, now),
        )
    _conn.commit()


def userbot_stats_today() -> dict:
    """Bugungi userbot statistikasi."""
    today = _now()[:10]
    total = _conn.execute("SELECT COUNT(*) c FROM userbot_chats").fetchone()["c"]
    new_today = _conn.execute(
        "SELECT COUNT(*) c FROM userbot_chats WHERE first_contact LIKE ?", (f"{today}%",)
    ).fetchone()["c"]
    active_today = _conn.execute(
        "SELECT COUNT(*) c FROM userbot_chats WHERE last_activity LIKE ?", (f"{today}%",)
    ).fetchone()["c"]
    escalated = _conn.execute(
        "SELECT COUNT(*) c FROM userbot_chats WHERE status='escalated'"
    ).fetchone()["c"]
    return {
        "total_clients": total,
        "new_today": new_today,
        "active_today": active_today,
        "escalated": escalated,
    }


# ---------------- Approvals ----------------
def create_approval(client_chat: int, draft: str) -> int:
    cur = _conn.execute(
        "INSERT INTO approvals(client_chat, draft, created_at) VALUES(?,?,?)",
        (client_chat, draft, _now()),
    )
    _conn.commit()
    return cur.lastrowid


def get_approval(approval_id: int) -> Optional[sqlite3.Row]:
    return _conn.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone()


def set_approval_status(approval_id: int, status: str) -> None:
    _conn.execute("UPDATE approvals SET status=? WHERE id=?", (status, approval_id))
    _conn.commit()


# ---------------- Payment screenshots ----------------
def create_payment_screenshot(client_chat: int, client_name: str) -> int:
    cur = _conn.execute(
        "INSERT INTO payment_screenshots(client_chat, client_name, created_at) VALUES(?,?,?)",
        (client_chat, client_name, _now()),
    )
    _conn.commit()
    return cur.lastrowid


def get_payment_screenshot(screenshot_id: int) -> Optional[sqlite3.Row]:
    return _conn.execute(
        "SELECT * FROM payment_screenshots WHERE id=?", (screenshot_id,)
    ).fetchone()


def set_payment_screenshot_status(screenshot_id: int, status: str) -> None:
    _conn.execute("UPDATE payment_screenshots SET status=? WHERE id=?", (status, screenshot_id))
    _conn.commit()


# ---------------- Follow-ups ----------------
def create_follow_up(chat_id: int, identifier: str, name: str) -> int:
    existing = _conn.execute(
        "SELECT id FROM follow_ups WHERE chat_id=? AND status='active'", (chat_id,)
    ).fetchone()
    if existing:
        return existing["id"]
    cur = _conn.execute(
        "INSERT INTO follow_ups(chat_id, identifier, name, attempts, last_attempt, created_at) "
        "VALUES(?,?,?,1,?,?)",
        (chat_id, identifier, name, _now(), _now()),
    )
    _conn.commit()
    return cur.lastrowid


def resolve_follow_up(chat_id: int) -> None:
    _conn.execute(
        "UPDATE follow_ups SET status='responded' WHERE chat_id=? AND status='active'", (chat_id,)
    )
    _conn.commit()


def get_pending_follow_ups() -> list:
    """24 soatdan ko'proq vaqt o'tgan, hali javob bermagan follow-uplar."""
    from datetime import datetime, timedelta
    cutoff = (datetime.now(config.TIMEZONE) - timedelta(hours=24)).isoformat()
    return _conn.execute(
        "SELECT * FROM follow_ups WHERE status='active' AND attempts < 3 "
        "AND last_attempt < ? ORDER BY last_attempt",
        (cutoff,)
    ).fetchall()


def increment_follow_up(follow_up_id: int) -> int:
    row = _conn.execute(
        "SELECT attempts FROM follow_ups WHERE id=?", (follow_up_id,)
    ).fetchone()
    new_attempts = (row["attempts"] if row else 0) + 1
    _conn.execute(
        "UPDATE follow_ups SET attempts=?, last_attempt=? WHERE id=?",
        (new_attempts, _now(), follow_up_id)
    )
    if new_attempts >= 3:
        # 3 urinish tugadi — yana 3 kun kutiladi, keyin 'archived' bo'ladi
        _conn.execute("UPDATE follow_ups SET status='max_attempts' WHERE id=?", (follow_up_id,))
    _conn.commit()
    return new_attempts


# ---------------- Leads ----------------

def add_lead(name: str, phone: str, category: str = None,
             city: str = None, address: str = None) -> bool:
    """Yangi lead qo'shadi. Telefon allaqachon mavjud bo'lsa False qaytaradi."""
    try:
        _conn.execute(
            "INSERT INTO leads(name, phone, category, city, address, created_at) "
            "VALUES(?,?,?,?,?,?)",
            (name, phone, category, city, address, _now()),
        )
        _conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def count_new_leads() -> int:
    return _conn.execute(
        "SELECT COUNT(*) c FROM leads WHERE status='new'"
    ).fetchone()["c"]


def get_new_leads(limit: int) -> list:
    return _conn.execute(
        "SELECT * FROM leads WHERE status='new' ORDER BY id LIMIT ?", (limit,)
    ).fetchall()


def mark_lead_sent(lead_id: int, telegram_chat_id: int = None) -> None:
    _conn.execute(
        "UPDATE leads SET status='sent', telegram_chat_id=?, sent_at=? WHERE id=?",
        (telegram_chat_id, _now(), lead_id),
    )
    _conn.commit()


def mark_lead_failed(lead_id: int) -> None:
    _conn.execute(
        "UPDATE leads SET status='failed', sent_at=? WHERE id=?",
        (_now(), lead_id),
    )
    _conn.commit()


def mark_lead_replied_by_chat_id(chat_id: int) -> None:
    """Mijoz javob berganda uning lead statusini 'replied' ga o'tkazadi."""
    _conn.execute(
        "UPDATE leads SET status='replied' "
        "WHERE telegram_chat_id=? AND status='sent'",
        (chat_id,),
    )
    _conn.commit()


def get_leads_stats_today() -> dict:
    today = _now()[:10]
    sent = _conn.execute(
        "SELECT COUNT(*) c FROM leads "
        "WHERE status IN ('sent','replied') AND sent_at LIKE ?",
        (f"{today}%",),
    ).fetchone()["c"]
    replied = _conn.execute(
        "SELECT COUNT(*) c FROM leads "
        "WHERE status='replied' AND sent_at LIKE ?",
        (f"{today}%",),
    ).fetchone()["c"]
    failed = _conn.execute(
        "SELECT COUNT(*) c FROM leads "
        "WHERE status='failed' AND sent_at LIKE ?",
        (f"{today}%",),
    ).fetchone()["c"]
    return {
        "sent": sent,
        "replied": replied,
        "no_reply": sent - replied,
        "failed": failed,
    }
