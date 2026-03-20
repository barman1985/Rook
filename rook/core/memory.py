"""
rook.core.memory — ACT-R inspired memory system
=================================================
Store, recall, and decay. Activation score = recency × frequency.

Usage:
    from rook.core.memory import memory

    memory.store("user_preference", "Likes jazz music", source="conversation")
    results = memory.recall("music preferences", limit=5)
"""

import math
import logging
from datetime import datetime

from rook.core.db import get_db, execute, execute_write

logger = logging.getLogger(__name__)


class Memory:
    """ACT-R inspired memory with activation scoring and decay."""

    def store(self, key: str, value: str, source: str = "user", confidence: float = 0.8) -> int:
        """Store a fact. Returns row ID."""
        return execute_write(
            "INSERT INTO memory (key, value, source, confidence) VALUES (?, ?, ?, ?)",
            (key, value, source, confidence)
        )

    def recall(self, query: str, limit: int = 5) -> list[dict]:
        """Recall memories matching query, sorted by activation score."""
        rows = execute(
            "SELECT * FROM memory WHERE key LIKE ? OR value LIKE ?",
            (f"%{query}%", f"%{query}%")
        )

        # Calculate activation score for each memory
        now = datetime.now()
        scored = []
        for row in rows:
            score = self._activation_score(row, now)
            row["activation"] = score
            scored.append(row)

        # Sort by activation (highest first) and return top N
        scored.sort(key=lambda x: x["activation"], reverse=True)
        results = scored[:limit]

        # Track access
        for r in results:
            self._track_access(r["id"])

        return results

    def _activation_score(self, row: dict, now: datetime) -> float:
        """
        ACT-R activation: B_i = ln(sum(t_j^{-d})) + noise
        Simplified: recency factor + frequency bonus
        """
        try:
            last_accessed = datetime.fromisoformat(row["last_accessed_at"])
        except (TypeError, ValueError):
            last_accessed = datetime.fromisoformat(row["created_at"])

        hours_since = max((now - last_accessed).total_seconds() / 3600, 0.1)
        access_count = row.get("access_count", 0) or 0
        confidence = row.get("confidence", 0.5)

        # Decay: older memories score lower
        decay = -0.5  # ACT-R default
        recency = math.pow(hours_since, decay)

        # Frequency: more accessed = higher score (logarithmic)
        frequency = math.log(1 + access_count) * 0.3

        return (recency + frequency) * confidence

    def _track_access(self, memory_id: int):
        """Update access time and count."""
        execute_write(
            "UPDATE memory SET last_accessed_at = datetime('now'), access_count = access_count + 1 WHERE id = ?",
            (memory_id,)
        )

    def decay(self, threshold: float = 0.01) -> int:
        """Remove memories below activation threshold. Returns count deleted."""
        rows = execute("SELECT * FROM memory")
        now = datetime.now()
        to_delete = []
        for row in rows:
            if self._activation_score(row, now) < threshold:
                to_delete.append(row["id"])

        if to_delete:
            placeholders = ",".join("?" * len(to_delete))
            execute_write(f"DELETE FROM memory WHERE id IN ({placeholders})", tuple(to_delete))
            logger.info(f"Memory decay: {len(to_delete)} memories removed")

        return len(to_delete)

    def count(self) -> int:
        """Total memory count."""
        result = execute("SELECT COUNT(*) as cnt FROM memory")
        return result[0]["cnt"] if result else 0

    def format_for_prompt(self, query: str, limit: int = 5) -> str:
        """Format recalled memories for LLM system prompt."""
        results = self.recall(query, limit=limit)
        if not results:
            return ""
        lines = ["Relevant memories:"]
        for r in results:
            lines.append(f"  - {r['key']}: {r['value']} (confidence: {r['confidence']:.0%})")
        return "\n".join(lines)


# Singleton
memory = Memory()
