"""
rook.core.emotional_memory — Emotional context tracking
==========================================================
Tracks valence/arousal/dominance per session, stores emotional imprints,
provides context for emotionally-aware responses.

Ported from Jarvis amygdala module, adapted for Rook patterns.

Usage:
    from rook.core.emotional_memory import emotions

    emotions.analyze_message("user", "I'm so frustrated with this!")
    context = emotions.get_emotional_context()
    mode = emotions.detect_mode()
"""

import re
import json
import logging
from datetime import datetime, timedelta

from rook.core.db import get_db, execute, execute_write

logger = logging.getLogger(__name__)

# ── Structural emotion detection (regex-based, zero API cost) ────────

_EMOTION_PATTERNS = {
    "joy": [
        r"\b(happy|glad|excited|love|great|awesome|amazing|wonderful|fantastic|yay)\b",
        r"[😊😄😃🎉❤️💚🥳🤩]",
        r"\b(thank|thanks|thx|díky|super|skvělé|paráda)\b",
    ],
    "frustration": [
        r"\b(frustrat\w+|annoying|angry|mad|hate|ugh|damn|shit|fuck)\b",
        r"[😤😡🤬💢]",
        r"\b(nefunguje|nejde|broken|stuck|wtf)\b",
    ],
    "sadness": [
        r"\b(sad|depressed|lonely|miss|crying|hurt|lost)\b",
        r"[😢😭😔💔]",
        r"\b(smutný|smutná|stýská|bolí)\b",
    ],
    "anxiety": [
        r"\b(worried|anxious|nervous|scared|afraid|stress|panic)\b",
        r"[😰😨😱]",
        r"\b(bojím|strach|stres|nervózní)\b",
    ],
    "focus": [
        r"\b(working on|building|coding|let's|implement|create|fix)\b",
        r"\b(dělám|pracuju|řeším|opravuju|stavím)\b",
    ],
    "curiosity": [
        r"\b(how|why|what if|wonder|curious|interesting|explain)\b",
        r"[🤔💡]",
        r"\b(jak|proč|zajímavé|vysvětli)\b",
    ],
}

_VALENCE_MAP = {
    "joy": 0.8, "curiosity": 0.3, "focus": 0.1,
    "anxiety": -0.4, "frustration": -0.6, "sadness": -0.7,
}
_AROUSAL_MAP = {
    "joy": 0.6, "frustration": 0.8, "anxiety": 0.7,
    "sadness": 0.3, "focus": 0.5, "curiosity": 0.4,
}


def _detect_emotions(text: str) -> list[str]:
    """Detect emotions from text using regex patterns. Returns list of emotion names."""
    text_lower = text.lower()
    detected = []
    for emotion, patterns in _EMOTION_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                detected.append(emotion)
                break
    return detected


class EmotionalMemory:
    """Tracks emotional state across conversation sessions."""

    def __init__(self):
        self._session_emotions: list[str] = []
        self._session_start: datetime = datetime.now()
        self._message_count: int = 0

    def analyze_message(self, role: str, text: str) -> dict:
        """
        Analyze emotional signals in a message. Tracks session state.
        Returns: {"emotions": [...], "valence": float, "arousal": float}
        """
        emotions = _detect_emotions(text)
        self._session_emotions.extend(emotions)
        self._message_count += 1

        if not emotions:
            return {"emotions": [], "valence": 0.0, "arousal": 0.0}

        valence = sum(_VALENCE_MAP.get(e, 0) for e in emotions) / len(emotions)
        arousal = sum(_AROUSAL_MAP.get(e, 0) for e in emotions) / len(emotions)

        return {"emotions": emotions, "valence": round(valence, 2), "arousal": round(arousal, 2)}

    def detect_mode(self) -> str:
        """
        Detect conversation mode from accumulated session emotions.
        Returns: "focused" | "playful" | "stressed" | "deep_talk" | "neutral"
        """
        if not self._session_emotions:
            return "neutral"

        counts = {}
        for e in self._session_emotions:
            counts[e] = counts.get(e, 0) + 1

        dominant = max(counts, key=counts.get)

        if dominant in ("focus",):
            return "focused"
        if dominant in ("joy", "curiosity"):
            return "playful"
        if dominant in ("frustration", "anxiety"):
            return "stressed"
        if dominant in ("sadness",):
            return "deep_talk"
        return "neutral"

    def consolidate_session(self) -> int | None:
        """
        Save current session as an emotional imprint (call at session end or daily).
        Returns imprint ID or None if session was empty.
        """
        if self._message_count < 3:
            return None

        emotions = self._session_emotions
        if not emotions:
            return None

        # Aggregate
        valence = sum(_VALENCE_MAP.get(e, 0) for e in emotions) / len(emotions) if emotions else 0
        arousal = sum(_AROUSAL_MAP.get(e, 0) for e in emotions) / len(emotions) if emotions else 0

        counts = {}
        for e in emotions:
            counts[e] = counts.get(e, 0) + 1
        dominant = max(counts, key=counts.get) if counts else "neutral"

        summary = f"Session ({self._message_count} msgs): dominant={dominant}, emotions={dict(counts)}"

        rid = execute_write(
            """INSERT INTO emotional_imprints
               (summary, valence, arousal, dominant_emotion, trigger, message_count)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (summary, round(valence, 3), round(arousal, 3), dominant,
             json.dumps(dict(counts)), self._message_count),
        )

        logger.info(f"Emotional imprint #{rid}: {dominant} (v={valence:.2f}, a={arousal:.2f})")

        # Reset session
        self._session_emotions = []
        self._message_count = 0
        self._session_start = datetime.now()

        return rid

    def get_emotional_context(self, max_imprints: int = 5, max_quotes: int = 3) -> str:
        """Build emotional context string for system prompt."""
        parts = []

        # Current session mood
        mode = self.detect_mode()
        if mode != "neutral":
            parts.append(f"Current conversation mood: {mode}")

        # Recent imprints
        imprints = execute(
            "SELECT * FROM emotional_imprints ORDER BY timestamp DESC LIMIT ?",
            (max_imprints,),
        )
        if imprints:
            parts.append("Recent emotional patterns:")
            for imp in imprints:
                parts.append(f"  [{imp['timestamp'][:10]}] {imp['dominant_emotion']} — {imp['summary'][:80]}")

        # Quotes
        quotes = execute(
            "SELECT text, emotion, context FROM emotional_quotes ORDER BY timestamp DESC LIMIT ?",
            (max_quotes,),
        )
        if quotes:
            parts.append("Notable quotes:")
            for q in quotes:
                parts.append(f'  "{q["text"][:60]}" ({q["emotion"]})')

        return "\n".join(parts) if parts else ""

    def save_quote(self, text: str, context: str = "", emotion: str = "", source: str = "user") -> int:
        """Save a meaningful quote with emotional context."""
        return execute_write(
            "INSERT INTO emotional_quotes (text, context, emotion, source) VALUES (?, ?, ?, ?)",
            (text, context, emotion, source),
        )

    def get_stats(self) -> dict:
        """Emotional memory statistics."""
        imprints = execute("SELECT COUNT(*) as cnt FROM emotional_imprints")
        quotes = execute("SELECT COUNT(*) as cnt FROM emotional_quotes")
        return {
            "total_imprints": imprints[0]["cnt"] if imprints else 0,
            "total_quotes": quotes[0]["cnt"] if quotes else 0,
            "session_messages": self._message_count,
            "session_mode": self.detect_mode(),
        }


# Singleton
emotions = EmotionalMemory()
