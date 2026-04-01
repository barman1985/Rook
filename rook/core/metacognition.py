"""
rook.core.metacognition — Self-awareness and confidence calibration
=====================================================================
Bayesian confidence tracking per domain using Beta distribution.
Rook knows what it's good at and what it's not.

Usage:
    from rook.core.metacognition import meta

    meta.record_outcome("calendar", success=True, score=0.9)
    conf = meta.estimate_confidence("calendar")
    brief = meta.get_metacognitive_brief()
"""

import math
import logging
from datetime import datetime

from rook.core.db import get_db, execute, execute_write

logger = logging.getLogger(__name__)

# Default domains — seeded on first use
DEFAULT_DOMAINS = [
    "calendar", "email", "web_search", "memory", "creative",
    "coding", "music", "tv", "medications", "general",
]


class Metacognition:
    """Bayesian confidence tracking using Beta distribution."""

    def estimate_confidence(self, domain: str) -> dict:
        """
        Estimate confidence for a domain.
        Returns: {confidence, uncertainty, ci_lower, ci_upper, alpha, beta, samples}
        """
        row = self._get_or_create(domain)
        alpha = row["alpha"]
        beta_ = row["beta"]

        confidence = alpha / (alpha + beta_) if (alpha + beta_) > 0 else 0.5
        n = alpha + beta_
        # Variance of Beta distribution
        variance = (alpha * beta_) / ((n ** 2) * (n + 1)) if n > 0 else 0.25
        uncertainty = math.sqrt(variance)

        # 95% credible interval (approximation)
        ci_lower = max(0.0, confidence - 1.96 * uncertainty)
        ci_upper = min(1.0, confidence + 1.96 * uncertainty)

        return {
            "confidence": round(confidence, 3),
            "uncertainty": round(uncertainty, 4),
            "ci_lower": round(ci_lower, 3),
            "ci_upper": round(ci_upper, 3),
            "alpha": alpha,
            "beta": beta_,
            "samples": int(alpha + beta_),
        }

    def record_outcome(self, domain: str, success: bool, score: float = 1.0):
        """
        Record a task outcome. Updates Beta distribution parameters.
        score: 0.0-1.0, partial success allowed.
        """
        row = self._get_or_create(domain)
        alpha = row["alpha"]
        beta_ = row["beta"]

        if success:
            alpha += score
        else:
            beta_ += (1.0 - score)

        execute_write(
            "UPDATE metacognition SET alpha = ?, beta = ?, last_updated = datetime('now') WHERE domain = ?",
            (round(alpha, 3), round(beta_, 3), domain),
        )

        # Log to capability_log
        execute_write(
            "INSERT INTO capability_log (domain, success, score) VALUES (?, ?, ?)",
            (domain, 1 if success else 0, round(score, 3)),
        )

        logger.debug(f"Metacognition [{domain}]: success={success}, score={score:.2f} → α={alpha:.1f}, β={beta_:.1f}")

    def get_calibration_report(self) -> str:
        """Full calibration report across all domains."""
        rows = execute("SELECT * FROM metacognition ORDER BY domain")
        if not rows:
            return "No metacognition data yet."

        lines = ["📊 Calibration Report:"]
        for r in rows:
            conf = self.estimate_confidence(r["domain"])
            bar = self._bar(conf["confidence"])
            lines.append(
                f"  {r['domain']:15s} {bar} {conf['confidence']:.0%} "
                f"(±{conf['uncertainty']:.1%}, n={conf['samples']})"
            )
        return "\n".join(lines)

    def get_metacognitive_brief(self) -> str:
        """Short summary for system prompt injection."""
        rows = execute("SELECT domain, alpha, beta FROM metacognition ORDER BY domain")
        if not rows:
            return ""

        strong = []
        weak = []
        for r in rows:
            n = r["alpha"] + r["beta"]
            if n < 3:
                continue  # Not enough data
            conf = r["alpha"] / n
            if conf >= 0.75:
                strong.append(r["domain"])
            elif conf < 0.5:
                weak.append(r["domain"])

        parts = []
        if strong:
            parts.append(f"Strong domains: {', '.join(strong)}")
        if weak:
            parts.append(f"Weaker domains: {', '.join(weak)}")
        return "\n".join(parts) if parts else ""

    def _get_or_create(self, domain: str) -> dict:
        """Get domain row, creating with priors if needed."""
        rows = execute("SELECT * FROM metacognition WHERE domain = ?", (domain,))
        if rows:
            return rows[0]

        # Prior: α=2, β=2 (uninformative, centered at 0.5)
        execute_write(
            "INSERT INTO metacognition (domain, alpha, beta) VALUES (?, ?, ?)",
            (domain, 2.0, 2.0),
        )
        return {"domain": domain, "alpha": 2.0, "beta": 2.0, "last_updated": None}

    @staticmethod
    def _bar(value: float, width: int = 10) -> str:
        """Visual bar: ████░░░░░░"""
        filled = round(value * width)
        return "█" * filled + "░" * (width - filled)


# Singleton
meta = Metacognition()
