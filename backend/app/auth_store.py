"""SQLite users + encrypted per-user API keys for hosted mode."""
from __future__ import annotations

import hashlib
import secrets
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.config import data_root, encryption_key_bytes, hosted_mode


@dataclass
class UserRecord:
    id: str
    email: str
    is_admin: bool
    created_at: str


def _db_path() -> Path:
    path = data_root() / "app.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                trial_runs_used INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS user_secrets (
                user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                openai_enc TEXT,
                xai_enc TEXT,
                google_fonts_enc TEXT,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS trial_guests (
                id TEXT PRIMARY KEY,
                runs_used INTEGER NOT NULL DEFAULT 0,
                stills_used INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS trial_daily (
                day TEXT PRIMARY KEY,
                runs_used INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        cols = {
            str(row[1])
            for row in conn.execute("PRAGMA table_info(users)").fetchall()
        }
        if "trial_runs_used" not in cols:
            conn.execute(
                "ALTER TABLE users ADD COLUMN trial_runs_used INTEGER NOT NULL DEFAULT 0"
            )
        if "trial_stills_used" not in cols:
            conn.execute(
                "ALTER TABLE users ADD COLUMN trial_stills_used INTEGER NOT NULL DEFAULT 0"
            )


def _hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt_bytes = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt_bytes,
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )
    return f"scrypt${salt_bytes.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt_hex, digest_hex = stored.split("$", 2)
    except ValueError:
        return False
    if algo != "scrypt":
        return False
    salt = bytes.fromhex(salt_hex)
    candidate = _hash_password(password, salt=salt)
    return secrets.compare_digest(candidate, stored)


def _fernet() -> Fernet:
    return Fernet(encryption_key_bytes())


def _encrypt(value: str | None) -> str | None:
    if not value:
        return None
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def _decrypt(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return None


def count_users() -> int:
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
        return int(row["n"] if row else 0)


def get_user_by_email(email: str) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE email = ? COLLATE NOCASE",
            (email.strip(),),
        ).fetchone()


def get_user_by_id(user_id: str) -> UserRecord | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, email, is_admin, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    if not row:
        return None
    return UserRecord(
        id=row["id"],
        email=row["email"],
        is_admin=bool(row["is_admin"]),
        created_at=row["created_at"],
    )


def create_user(email: str, password: str, *, is_admin: bool = False) -> UserRecord:
    email_norm = email.strip().lower()
    if not email_norm or "@" not in email_norm:
        raise ValueError("Valid email required")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    if get_user_by_email(email_norm):
        raise ValueError("User already exists")
    user_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO users (id, email, password_hash, is_admin, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, email_norm, _hash_password(password), 1 if is_admin else 0, now),
        )
    return UserRecord(id=user_id, email=email_norm, is_admin=is_admin, created_at=now)


def authenticate(email: str, password: str) -> UserRecord | None:
    row = get_user_by_email(email)
    if not row:
        return None
    if not verify_password(password, row["password_hash"]):
        return None
    return UserRecord(
        id=row["id"],
        email=row["email"],
        is_admin=bool(row["is_admin"]),
        created_at=row["created_at"],
    )


def set_password(email: str, password: str) -> UserRecord:
    """Overwrite password hash for an existing account."""
    email_norm = email.strip().lower()
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    row = get_user_by_email(email_norm)
    if not row:
        raise ValueError("User not found")
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (_hash_password(password), row["id"]),
        )
    return UserRecord(
        id=row["id"],
        email=row["email"],
        is_admin=bool(row["is_admin"]),
        created_at=row["created_at"],
    )


def load_user_keys(user_id: str) -> dict[str, str]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT openai_enc, xai_enc, google_fonts_enc FROM user_secrets WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if not row:
        return {}
    out: dict[str, str] = {}
    openai = _decrypt(row["openai_enc"])
    xai = _decrypt(row["xai_enc"])
    google = _decrypt(row["google_fonts_enc"])
    if openai:
        out["openai_api_key"] = openai
    if xai:
        out["xai_api_key"] = xai
    if google:
        out["google_fonts_api_key"] = google
    return out


def update_user_keys(
    user_id: str,
    *,
    openai_api_key: str | None = None,
    xai_api_key: str | None = None,
    google_fonts_api_key: str | None = None,
    clear_openai: bool = False,
    clear_xai: bool = False,
    clear_google_fonts: bool = False,
) -> dict[str, str]:
    current = load_user_keys(user_id)
    if clear_openai:
        current.pop("openai_api_key", None)
    elif openai_api_key is not None:
        trimmed = openai_api_key.strip()
        if trimmed:
            current["openai_api_key"] = trimmed
    if clear_xai:
        current.pop("xai_api_key", None)
    elif xai_api_key is not None:
        trimmed = xai_api_key.strip()
        if trimmed:
            current["xai_api_key"] = trimmed
    if clear_google_fonts:
        current.pop("google_fonts_api_key", None)
    elif google_fonts_api_key is not None:
        trimmed = google_fonts_api_key.strip()
        if trimmed:
            current["google_fonts_api_key"] = trimmed

    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO user_secrets (user_id, openai_enc, xai_enc, google_fonts_enc, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                openai_enc = excluded.openai_enc,
                xai_enc = excluded.xai_enc,
                google_fonts_enc = excluded.google_fonts_enc,
                updated_at = excluded.updated_at
            """,
            (
                user_id,
                _encrypt(current.get("openai_api_key")),
                _encrypt(current.get("xai_api_key")),
                _encrypt(current.get("google_fonts_api_key")),
                now,
            ),
        )
    return current


def create_guest_trial(guest_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO trial_guests (id, runs_used, stills_used, created_at, last_seen_at)
            VALUES (?, 0, 0, ?, ?)
            """,
            (guest_id, now, now),
        )


def get_guest_trial(guest_id: str) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM trial_guests WHERE id = ?",
            (guest_id,),
        ).fetchone()


def increment_guest_trial(guest_id: str, *, stills: int = 0) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """
            UPDATE trial_guests
            SET runs_used = COALESCE(runs_used, 0) + 1,
                stills_used = COALESCE(stills_used, 0) + ?,
                last_seen_at = ?
            WHERE id = ?
            """,
            (max(0, stills), now, guest_id),
        )


def today_global_trial_runs() -> int:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with _connect() as conn:
        row = conn.execute(
            "SELECT runs_used FROM trial_daily WHERE day = ?",
            (day,),
        ).fetchone()
    if not row:
        return 0
    try:
        return max(0, int(row["runs_used"] or 0))
    except (TypeError, ValueError):
        return 0


def increment_global_trial_run() -> None:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO trial_daily (day, runs_used) VALUES (?, 1)
            ON CONFLICT(day) DO UPDATE SET runs_used = runs_used + 1
            """,
            (day,),
        )


def get_trial_runs_used(user_id: str) -> int:
    with _connect() as conn:
        row = conn.execute(
            "SELECT trial_runs_used FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    if not row:
        return 0
    try:
        return max(0, int(row["trial_runs_used"] or 0))
    except (TypeError, ValueError):
        return 0


def get_trial_stills_used(user_id: str) -> int:
    with _connect() as conn:
        row = conn.execute(
            "SELECT trial_stills_used FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    if not row:
        return 0
    try:
        return max(0, int(row["trial_stills_used"] or 0))
    except (TypeError, ValueError, KeyError, IndexError):
        return 0


def increment_trial_runs_used(user_id: str) -> int:
    return increment_trial_usage(user_id, stills=0)


def increment_trial_usage(user_id: str, *, stills: int = 0) -> int:
    with _connect() as conn:
        conn.execute(
            """
            UPDATE users
            SET trial_runs_used = COALESCE(trial_runs_used, 0) + 1,
                trial_stills_used = COALESCE(trial_stills_used, 0) + ?
            WHERE id = ?
            """,
            (max(0, stills), user_id),
        )
        row = conn.execute(
            "SELECT trial_runs_used FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    return int(row["trial_runs_used"] if row else 0)


def bootstrap_admin_from_env() -> dict[str, Any] | None:
    """Create the first admin from BOOTSTRAP_ADMIN_EMAIL / PASSWORD when DB is empty.

    Set FORCE_BOOTSTRAP_PASSWORD=1 to overwrite that admin's password on startup
    (then turn the flag off so later deploys do not keep resetting it).
    """
    if not hosted_mode():
        return None
    import os

    email = (os.getenv("BOOTSTRAP_ADMIN_EMAIL") or "").strip()
    password = (os.getenv("BOOTSTRAP_ADMIN_PASSWORD") or "").strip()
    if not email or not password:
        return None
    force = (os.getenv("FORCE_BOOTSTRAP_PASSWORD") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if count_users() > 0:
        if not force:
            return None
        user = set_password(email, password)
        return {"updated": True, "email": user.email, "id": user.id}
    user = create_user(email, password, is_admin=True)
    return {"created": True, "email": user.email, "id": user.id}
