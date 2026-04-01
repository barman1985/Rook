"""
rook.services.discovery — Proactive content discovery
========================================================
Scans RSS feeds, scores relevance via FREE LLM classify,
notifies user about interesting findings. Max 3 notifications/day.

Usage:
    from rook.services.discovery import discovery

    await discovery.run_discovery()
    discovery.add_source("https://news.ycombinator.com/rss", "Hacker News", "tech")
    recent = discovery.get_recent_discoveries(limit=5)
"""

import logging
from datetime import datetime, date

from rook.core.db import execute, execute_write
from rook.core.events import bus

logger = logging.getLogger(__name__)

# Limits
MAX_NOTIFICATIONS_PER_DAY = 3
RELEVANCE_THRESHOLD = 0.6

# Default RSS sources (user can add more)
_DEFAULT_SOURCES = [
    ("https://news.ycombinator.com/rss", "Hacker News", "tech"),
    ("https://feeds.arstechnica.com/arstechnica/index", "Ars Technica", "tech"),
    ("https://www.reddit.com/r/LocalLLaMA/.rss", "r/LocalLLaMA", "ai"),
]


class Discovery:
    """Proactive content discovery via RSS feeds."""

    def __init__(self):
        self._notified_today: int = 0
        self._notified_date: date | None = None

    def _reset_daily_counter(self):
        today = date.today()
        if self._notified_date != today:
            self._notified_today = 0
            self._notified_date = today

    async def run_discovery(self):
        """
        Main discovery pipeline. Called by scheduler (4x/day).
        1. Fetch RSS feeds
        2. Filter already-seen items
        3. Score relevance via LLM classify
        4. Notify if score > threshold (max 3/day)
        """
        self._reset_daily_counter()

        if self._notified_today >= MAX_NOTIFICATIONS_PER_DAY:
            logger.debug("Discovery: daily notification limit reached")
            return

        sources = self._get_enabled_sources()
        if not sources:
            self._seed_default_sources()
            sources = self._get_enabled_sources()

        if not sources:
            logger.debug("Discovery: no sources configured")
            return

        new_items = []
        for source in sources:
            items = self._fetch_feed(source["url"], source["name"], source["category"])
            new_items.extend(items)

        if not new_items:
            logger.debug("Discovery: no new items")
            return

        # Score and notify
        for item in new_items[:10]:  # Process max 10 new items per run
            if self._notified_today >= MAX_NOTIFICATIONS_PER_DAY:
                break

            score = await self._score_relevance(item)
            self._save_item(item, score)

            if score >= RELEVANCE_THRESHOLD:
                await self._notify(item, score)
                self._notified_today += 1

        logger.info(f"Discovery: processed {len(new_items)} items, notified {self._notified_today} today")

    def add_source(self, url: str, name: str, category: str = "general") -> int:
        """Add an RSS source."""
        existing = execute("SELECT id FROM discovery_sources WHERE url = ?", (url,))
        if existing:
            return existing[0]["id"]
        return execute_write(
            "INSERT INTO discovery_sources (url, name, category, enabled) VALUES (?, ?, ?, 1)",
            (url, name, category),
        )

    def remove_source(self, url: str) -> bool:
        """Disable an RSS source."""
        from rook.core.db import get_db
        with get_db() as conn:
            cursor = conn.execute("UPDATE discovery_sources SET enabled = 0 WHERE url = ?", (url,))
            conn.commit()
            return cursor.rowcount > 0

    def get_recent_discoveries(self, limit: int = 5) -> str:
        """Format recent discoveries for prompt or display."""
        rows = execute(
            "SELECT title, summary, score, timestamp FROM discovery_items WHERE notified = 1 ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )
        if not rows:
            return ""
        lines = ["Recent discoveries:"]
        for r in rows:
            lines.append(f"  [{r['timestamp'][:10]}] {r['title'][:60]} (relevance: {r['score']:.0%})")
            if r["summary"]:
                lines.append(f"    {r['summary'][:100]}")
        return "\n".join(lines)

    def get_sources(self) -> list[dict]:
        """List all RSS sources."""
        return execute("SELECT * FROM discovery_sources ORDER BY category, name")

    def _get_enabled_sources(self) -> list[dict]:
        return execute("SELECT * FROM discovery_sources WHERE enabled = 1")

    def _seed_default_sources(self):
        """Seed default RSS sources on first run."""
        for url, name, cat in _DEFAULT_SOURCES:
            self.add_source(url, name, cat)
        logger.info(f"Discovery: seeded {len(_DEFAULT_SOURCES)} default sources")

    def _fetch_feed(self, url: str, source_name: str, category: str) -> list[dict]:
        """Fetch and parse an RSS feed. Returns new (unseen) items."""
        try:
            import feedparser
        except ImportError:
            logger.debug("feedparser not installed — RSS discovery disabled")
            return []

        try:
            feed = feedparser.parse(url)
        except Exception as e:
            logger.warning(f"RSS fetch error [{source_name}]: {e}")
            return []

        new_items = []
        for entry in feed.entries[:15]:  # Max 15 entries per feed
            link = entry.get("link", "")
            if not link:
                continue

            # Check if already seen
            existing = execute("SELECT id FROM discovery_items WHERE url = ?", (link,))
            if existing:
                continue

            new_items.append({
                "url": link,
                "title": entry.get("title", "(no title)")[:200],
                "summary": entry.get("summary", "")[:500],
                "source": source_name,
                "category": category,
            })

        return new_items

    async def _score_relevance(self, item: dict) -> float:
        """Score item relevance using FREE LLM classify."""
        try:
            from rook.core.llm import llm
            prompt = (
                f"Rate the relevance of this article for a tech-savvy AI enthusiast (0.0-1.0):\n"
                f"Title: {item['title']}\n"
                f"Summary: {item['summary'][:200]}\n"
                f"Category: {item['category']}\n\n"
                f"Reply with ONLY a number between 0.0 and 1.0."
            )
            response = await llm.classify(prompt, system="You are a relevance scorer. Reply with only a decimal number.")
            score = float(response.strip().split()[0])
            return max(0.0, min(1.0, score))
        except Exception as e:
            logger.debug(f"Scoring error: {e}")
            return 0.5  # Default score on failure

    def _save_item(self, item: dict, score: float):
        """Save a discovery item to DB."""
        execute_write(
            "INSERT INTO discovery_items (url, title, summary, score, source, notified) VALUES (?, ?, ?, ?, ?, 0)",
            (item["url"], item["title"], item["summary"][:500], round(score, 3), item.get("source", "")),
        )

    async def _notify(self, item: dict, score: float):
        """Send notification about a relevant discovery."""
        text = f"🔍 {item['title']}\n{item['url']}\n(relevance: {score:.0%}, source: {item.get('source', '')})"
        execute_write(
            "UPDATE discovery_items SET notified = 1 WHERE url = ?",
            (item["url"],),
        )
        await bus.emit("notification.send", {"text": text})
        logger.info(f"Discovery notified: {item['title'][:50]}")


# Singleton
discovery = Discovery()
