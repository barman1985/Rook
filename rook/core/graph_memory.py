"""
rook.core.graph_memory — Entity-relation knowledge graph
==========================================================
Stores subject-predicate-object triples with confidence scoring.
"User → works_at → Freelance", "Rook → built_with → Python".

Usage:
    from rook.core.graph_memory import graph

    graph.add("User", "lives_in", "Prague", confidence=0.9, source="conversation")
    relations = graph.query("User")
    context = graph.format_for_prompt(max_items=10)
"""

import logging
from datetime import datetime

from rook.core.db import get_db, execute, execute_write

logger = logging.getLogger(__name__)


class GraphMemory:
    """Entity-relation graph backed by SQLite."""

    def add(
        self,
        subject: str,
        predicate: str,
        obj: str,
        confidence: float = 0.8,
        source: str = "conversation",
    ) -> int:
        """
        Add or update a relation.
        If subject+predicate+object exists, update confidence and timestamp.
        Returns row ID.
        """
        existing = execute(
            "SELECT id FROM knowledge_graph WHERE subject = ? AND predicate = ? AND object = ?",
            (subject, predicate, obj),
        )
        if existing:
            execute_write(
                "UPDATE knowledge_graph SET confidence = ?, source = ?, updated_at = datetime('now') WHERE id = ?",
                (confidence, source, existing[0]["id"]),
            )
            logger.debug(f"Graph updated: {subject} → {predicate} → {obj}")
            return existing[0]["id"]

        rid = execute_write(
            "INSERT INTO knowledge_graph (subject, predicate, object, confidence, source) VALUES (?, ?, ?, ?, ?)",
            (subject, predicate, obj, confidence, source),
        )
        logger.debug(f"Graph added: {subject} → {predicate} → {obj}")
        return rid

    def query(self, entity: str, limit: int = 20) -> list[dict]:
        """Query all relations where entity is subject OR object."""
        return execute(
            """SELECT * FROM knowledge_graph
               WHERE subject = ? OR object = ?
               ORDER BY confidence DESC, updated_at DESC
               LIMIT ?""",
            (entity, entity, limit),
        )

    def search(self, text: str, limit: int = 10) -> list[dict]:
        """Full-text search across subject, predicate, object."""
        pattern = f"%{text}%"
        return execute(
            """SELECT * FROM knowledge_graph
               WHERE subject LIKE ? OR predicate LIKE ? OR object LIKE ?
               ORDER BY confidence DESC
               LIMIT ?""",
            (pattern, pattern, pattern, limit),
        )

    def remove(self, subject: str, predicate: str, obj: str) -> bool:
        """Remove a specific relation. Returns True if deleted."""
        with get_db() as conn:
            cursor = conn.execute(
                "DELETE FROM knowledge_graph WHERE subject = ? AND predicate = ? AND object = ?",
                (subject, predicate, obj),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_stats(self) -> dict:
        """Graph statistics."""
        rows = execute("SELECT COUNT(*) as cnt FROM knowledge_graph")
        total = rows[0]["cnt"] if rows else 0
        subjects = execute("SELECT COUNT(DISTINCT subject) as cnt FROM knowledge_graph")
        predicates = execute("SELECT COUNT(DISTINCT predicate) as cnt FROM knowledge_graph")
        return {
            "total_relations": total,
            "unique_subjects": subjects[0]["cnt"] if subjects else 0,
            "unique_predicates": predicates[0]["cnt"] if predicates else 0,
        }

    def format_for_prompt(self, max_items: int = 15) -> str:
        """Format top relations for LLM system prompt injection."""
        rows = execute(
            "SELECT subject, predicate, object, confidence FROM knowledge_graph ORDER BY confidence DESC, updated_at DESC LIMIT ?",
            (max_items,),
        )
        if not rows:
            return ""
        lines = ["Knowledge graph:"]
        for r in rows:
            lines.append(f"  {r['subject']} → {r['predicate']} → {r['object']} ({r['confidence']:.0%})")
        return "\n".join(lines)


# Singleton
graph = GraphMemory()
