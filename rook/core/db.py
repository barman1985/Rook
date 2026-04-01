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

            -- Knowledge graph (entity-relation triples)
            CREATE TABLE IF NOT EXISTS knowledge_graph (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                subject     TEXT NOT NULL,
                predicate   TEXT NOT NULL,
                object      TEXT NOT NULL,
                confidence  REAL DEFAULT 0.8,
                source      TEXT DEFAULT 'conversation',
                created_at  TEXT DEFAULT (datetime('now')),
                updated_at  TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_kg_subject ON knowledge_graph(subject);
            CREATE INDEX IF NOT EXISTS idx_kg_object ON knowledge_graph(object);

            -- Emotional imprints (consolidated session emotions)
            CREATE TABLE IF NOT EXISTS emotional_imprints (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                summary           TEXT NOT NULL,
                valence           REAL DEFAULT 0.0,
                arousal           REAL DEFAULT 0.0,
                dominant_emotion  TEXT DEFAULT 'neutral',
                trigger           TEXT DEFAULT '',
                message_count     INTEGER DEFAULT 0,
                timestamp         TEXT DEFAULT (datetime('now'))
            );

            -- Emotional quotes (memorable quotes with emotional context)
            CREATE TABLE IF NOT EXISTS emotional_quotes (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                text      TEXT NOT NULL,
                context   TEXT DEFAULT '',
                emotion   TEXT DEFAULT '',
                source    TEXT DEFAULT 'user',
                timestamp TEXT DEFAULT (datetime('now'))
            );

            -- Metacognition (Bayesian confidence per domain)
            CREATE TABLE IF NOT EXISTS metacognition (
                domain       TEXT PRIMARY KEY,
                alpha        REAL DEFAULT 2.0,
                beta         REAL DEFAULT 2.0,
                last_updated TEXT DEFAULT (datetime('now'))
            );

            -- Capability log (individual task outcomes)
            CREATE TABLE IF NOT EXISTS capability_log (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                domain    TEXT NOT NULL,
                success   INTEGER DEFAULT 1,
                score     REAL DEFAULT 1.0,
                timestamp TEXT DEFAULT (datetime('now'))
            );

            -- A2A peers (known agent peers)
            CREATE TABLE IF NOT EXISTS a2a_peers (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id    TEXT NOT NULL UNIQUE,
                name        TEXT DEFAULT '',
                url         TEXT DEFAULT '',
                card_json   TEXT DEFAULT '{}',
                trust_score REAL DEFAULT 0.3,
                last_seen   TEXT DEFAULT (datetime('now'))
            );

            -- A2A exchanges (communication log)
            CREATE TABLE IF NOT EXISTS a2a_exchanges (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                direction TEXT NOT NULL,
                agent_id  TEXT NOT NULL,
                topic     TEXT DEFAULT '',
                question  TEXT DEFAULT '',
                response  TEXT DEFAULT '',
                relevance REAL DEFAULT 0.0,
                timestamp TEXT DEFAULT (datetime('now'))
            );

            -- Discovery items (found via RSS)
            CREATE TABLE IF NOT EXISTS discovery_items (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                url       TEXT NOT NULL UNIQUE,
                title     TEXT DEFAULT '',
                summary   TEXT DEFAULT '',
                score     REAL DEFAULT 0.0,
                source    TEXT DEFAULT '',
                notified  INTEGER DEFAULT 0,
                timestamp TEXT DEFAULT (datetime('now'))
            );

            -- Discovery sources (RSS feeds)
            CREATE TABLE IF NOT EXISTS discovery_sources (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                url      TEXT NOT NULL UNIQUE,
                name     TEXT DEFAULT '',
                category TEXT DEFAULT 'general',
                enabled  INTEGER DEFAULT 1
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


# ── Conversation management ──────────────────────────────────

def get_message_count() -> int:
    """Return total number of conversation messages."""
    rows = execute("SELECT COUNT(*) as cnt FROM messages")
    return rows[0]["cnt"] if rows else 0


def get_recent_messages(limit: int = 20) -> list[dict]:
    """Return the most recent N messages, oldest first."""
    return execute(
        "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?",
        (limit,)
    )[::-1]  # reverse to get chronological order


def delete_old_messages(keep_latest: int = 20) -> int:
    """Delete all messages except the latest N. Returns count deleted."""
    total = get_message_count()
    if total <= keep_latest:
        return 0
    with get_db() as conn:
        conn.execute("""
            DELETE FROM messages WHERE id NOT IN (
                SELECT id FROM messages ORDER BY id DESC LIMIT ?
            )
        """, (keep_latest,))
        conn.commit()
    deleted = total - keep_latest
    logger.info(f"Compaction: deleted {deleted} old messages, kept {keep_latest}")
    return deleted


def save_profile(key: str, value: str):
    """Save a user profile key-value pair (upsert)."""
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO user_profile (key, value, updated_at) VALUES (?, ?, datetime('now'))",
            (key, value)
        )
        conn.commit()


def get_profile(key: str, default=None):
    """Get a user profile value."""
    rows = execute("SELECT value FROM user_profile WHERE key = ?", (key,))
    return rows[0]["value"] if rows else default
