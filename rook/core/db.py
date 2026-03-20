"""
rook.core.db — Centralized database access
============================================
Every module uses this. No direct sqlite3.connect() anywhere else.

Usage:
    from rook.core.db import get_db, init_db

    with get_db() as conn:
        conn.execute("SELECT ...")
"""

import sqlite3
import logging
from contextlib import contextmanager
from pathlib import Path

from rook.core.config import cfg

logger = logging.getLogger(__name__)

_DB_PATH = cfg.db_path


def init_db():
    """Initialize all tables. Called once at startup."""
    with get_db() as conn:
        conn.executescript("""
            -- Conversations
            CREATE TABLE IF NOT EXISTS messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                role        TEXT NOT NULL,
                content     TEXT NOT NULL,
                timestamp   TEXT DEFAULT (datetime('now')),
                token_count INTEGER DEFAULT 0
            );

            -- Agent memory (ACT-R)
            CREATE TABLE IF NOT EXISTS memory (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                key             TEXT NOT NULL,
                value           TEXT NOT NULL,
                source          TEXT DEFAULT 'user',
                confidence      REAL DEFAULT 0.8,
                created_at      TEXT DEFAULT (datetime('now')),
                last_accessed_at TEXT DEFAULT (datetime('now')),
                access_count    INTEGER DEFAULT 0
            );

            -- User profile
            CREATE TABLE IF NOT EXISTS user_profile (
                key         TEXT PRIMARY KEY,
                value       TEXT NOT NULL,
                updated_at  TEXT DEFAULT (datetime('now'))
            );

            -- Event log (for proactive features)
            CREATE TABLE IF NOT EXISTS event_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type  TEXT NOT NULL,
                data        TEXT,
                timestamp   TEXT DEFAULT (datetime('now'))
            );
        """)
        conn.commit()
    logger.info("Database initialized")


@contextmanager
def get_db():
    """Get a database connection with WAL mode and row factory."""
    conn = sqlite3.connect(_DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()


def execute(query: str, params: tuple = ()) -> list[dict]:
    """Execute query and return results as list of dicts."""
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def execute_write(query: str, params: tuple = ()) -> int:
    """Execute write query and return lastrowid."""
    with get_db() as conn:
        cursor = conn.execute(query, params)
        conn.commit()
        return cursor.lastrowid
