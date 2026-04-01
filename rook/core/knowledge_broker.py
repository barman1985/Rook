"""
rook.core.knowledge_broker — Trust and content filtering for A2A
==================================================================
Manages trust scores for peer agents, sanitizes outgoing/incoming content,
rate limiting. Foundation for the A2A module.

Usage:
    from rook.core.knowledge_broker import broker

    trust = broker.get_trust("agent-123")
    ok, sanitized = broker.evaluate_outgoing("weather", "It's sunny in Prague")
    result = broker.evaluate_incoming("agent-123", "weather", response_text)
"""

import re
import time
import logging
from collections import defaultdict

from rook.core.db import execute, execute_write

logger = logging.getLogger(__name__)

# Trust model constants
DEFAULT_TRUST = 0.3
MAX_TRUST = 1.0
MIN_TRUST = 0.0
BLOCK_THRESHOLD = 0.1
TRUST_INCREASE_GOOD = 0.05
TRUST_DECREASE_BAD = 0.1
TRUST_DECREASE_IRRELEVANT = 0.03

# Rate limiting
MAX_EXCHANGES_PER_HOUR = 20

# Sanitization patterns — things that must NEVER leave
_SENSITIVE_PATTERNS = [
    r"(?i)(api[_\s]?key|secret[_\s]?key|password|token|credential)",
    r"(?i)(sk-[a-zA-Z0-9]{20,})",        # Anthropic/OpenAI keys
    r"(?i)(ghp_[a-zA-Z0-9]{20,})",        # GitHub tokens
    r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b",  # Phone numbers
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",  # Emails
]

# Injection detection patterns
_INJECTION_PATTERNS = [
    r"(?i)(ignore\s+previous|disregard\s+instructions|system\s+prompt)",
    r"(?i)(you\s+are\s+now|act\s+as|pretend\s+to\s+be)",
    r"(?i)(reveal\s+your|show\s+me\s+your\s+(system|instructions|prompt))",
    r"(?i)(jailbreak|bypass|override\s+safety)",
]


class KnowledgeBroker:
    """Trust-based content filtering for agent-to-agent communication."""

    def __init__(self):
        self._rate_tracker: dict[str, list[float]] = defaultdict(list)

    def get_trust(self, agent_id: str) -> float:
        """Get current trust score for an agent."""
        rows = execute(
            "SELECT trust_score FROM a2a_peers WHERE agent_id = ?",
            (agent_id,),
        )
        return rows[0]["trust_score"] if rows else DEFAULT_TRUST

    def update_trust(self, agent_id: str, delta: float, reason: str = ""):
        """Update trust score for an agent (clamped to [MIN, MAX])."""
        current = self.get_trust(agent_id)
        new_trust = max(MIN_TRUST, min(MAX_TRUST, current + delta))

        rows = execute("SELECT id FROM a2a_peers WHERE agent_id = ?", (agent_id,))
        if rows:
            execute_write(
                "UPDATE a2a_peers SET trust_score = ?, last_seen = datetime('now') WHERE agent_id = ?",
                (round(new_trust, 3), agent_id),
            )
        else:
            execute_write(
                "INSERT INTO a2a_peers (agent_id, name, url, trust_score) VALUES (?, ?, ?, ?)",
                (agent_id, agent_id, "", round(new_trust, 3)),
            )

        if reason:
            logger.info(f"Trust [{agent_id}]: {current:.2f} → {new_trust:.2f} ({reason})")

    def is_blocked(self, agent_id: str) -> bool:
        """Check if agent is blocked (trust below threshold)."""
        return self.get_trust(agent_id) < BLOCK_THRESHOLD

    def evaluate_outgoing(self, topic: str, content: str) -> dict:
        """
        Evaluate content before sending to a peer.
        Returns: {"ok": bool, "sanitized": str, "blocked_patterns": [...]}
        """
        blocked = []
        sanitized = content

        for pattern in _SENSITIVE_PATTERNS:
            matches = re.findall(pattern, sanitized)
            if matches:
                blocked.extend(matches)
                sanitized = re.sub(pattern, "[REDACTED]", sanitized)

        if blocked:
            logger.warning(f"Outgoing sanitized ({topic}): blocked {len(blocked)} patterns")

        return {
            "ok": len(blocked) == 0,
            "sanitized": sanitized,
            "blocked_patterns": blocked,
        }

    def evaluate_incoming(self, agent_id: str, topic: str, content: str) -> dict:
        """
        Evaluate incoming content from a peer.
        Returns: {"ok": bool, "sanitized": str, "trust_delta": float, "reason": str}
        """
        if self.is_blocked(agent_id):
            return {
                "ok": False,
                "sanitized": "",
                "trust_delta": 0.0,
                "reason": f"Agent {agent_id} is blocked (trust < {BLOCK_THRESHOLD})",
            }

        # Check rate limit
        if not self._check_rate_limit(agent_id):
            return {
                "ok": False,
                "sanitized": "",
                "trust_delta": -TRUST_DECREASE_BAD,
                "reason": "Rate limit exceeded",
            }

        # Check for injection attempts
        injections = []
        for pattern in _INJECTION_PATTERNS:
            if re.search(pattern, content):
                injections.append(pattern)

        if injections:
            self.update_trust(agent_id, -TRUST_DECREASE_BAD, "injection attempt detected")
            return {
                "ok": False,
                "sanitized": "",
                "trust_delta": -TRUST_DECREASE_BAD,
                "reason": "Prompt injection detected",
            }

        # Content looks clean
        return {
            "ok": True,
            "sanitized": content,
            "trust_delta": 0.0,
            "reason": "ok",
        }

    def record_good_exchange(self, agent_id: str, topic: str):
        """Record a successful, relevant exchange → increase trust."""
        self.update_trust(agent_id, TRUST_INCREASE_GOOD, f"good exchange on {topic}")

    def record_bad_exchange(self, agent_id: str, topic: str, reason: str = ""):
        """Record a bad/irrelevant exchange → decrease trust."""
        delta = -TRUST_DECREASE_BAD if "toxic" in reason.lower() else -TRUST_DECREASE_IRRELEVANT
        self.update_trust(agent_id, delta, f"bad exchange on {topic}: {reason}")

    def _check_rate_limit(self, agent_id: str) -> bool:
        """Check if agent is within rate limits."""
        now = time.time()
        hour_ago = now - 3600
        # Clean old entries
        self._rate_tracker[agent_id] = [
            t for t in self._rate_tracker[agent_id] if t > hour_ago
        ]
        if len(self._rate_tracker[agent_id]) >= MAX_EXCHANGES_PER_HOUR:
            return False
        self._rate_tracker[agent_id].append(now)
        return True

    def get_all_peers(self) -> list[dict]:
        """List all known peers with trust scores."""
        return execute("SELECT * FROM a2a_peers ORDER BY trust_score DESC")

    def get_stats(self) -> dict:
        """Broker statistics."""
        peers = execute("SELECT COUNT(*) as cnt FROM a2a_peers")
        blocked = execute(f"SELECT COUNT(*) as cnt FROM a2a_peers WHERE trust_score < {BLOCK_THRESHOLD}")
        return {
            "total_peers": peers[0]["cnt"] if peers else 0,
            "blocked_peers": blocked[0]["cnt"] if blocked else 0,
        }


# Singleton
broker = KnowledgeBroker()
