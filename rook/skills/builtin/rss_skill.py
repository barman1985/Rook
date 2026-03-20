"""
Built-in skill: RSS reader
============================
Read and parse RSS/Atom feeds.
"""

import re
import logging

from rook.skills.base import Skill, tool

logger = logging.getLogger(__name__)


class RSSSkill(Skill):
    name = "rss"
    description = "Read RSS/Atom feeds"
    version = "1.0"

    @tool(
        "read_rss",
        "Read an RSS or Atom feed and return articles",
        {"type": "object", "properties": {
            "url": {"type": "string", "description": "Feed URL"},
            "limit": {"type": "integer", "description": "Max articles (default 10, max 25)"},
        }, "required": ["url"]}
    )
    def read_rss(self, url: str, limit: int = 10) -> str:
        try:
            import feedparser
        except ImportError:
            return "feedparser not installed. Run: pip install feedparser"

        limit = max(1, min(25, limit))
        feed = feedparser.parse(url)

        if feed.bozo and not feed.entries:
            err = str(getattr(feed, "bozo_exception", "unknown"))[:200]
            return f"Feed parse error for {url}: {err}"

        if not feed.entries:
            return f"Feed {url} has no articles."

        title = feed.feed.get("title", url)
        lines = [f"{title} ({min(limit, len(feed.entries))} of {len(feed.entries)} articles):"]

        for i, entry in enumerate(feed.entries[:limit]):
            etitle = entry.get("title", "(no title)")
            link = entry.get("link", "")
            published = entry.get("published", entry.get("updated", ""))

            summary = entry.get("summary", entry.get("description", ""))
            if summary:
                summary = re.sub(r"<[^>]+>", "", summary).strip()
                if len(summary) > 200:
                    summary = summary[:200] + "..."

            lines.append(f"\n{i+1}. {etitle}")
            if published:
                lines.append(f"   {published[:25]}")
            if summary:
                lines.append(f"   {summary}")
            if link:
                lines.append(f"   {link}")

        return "\n".join(lines)


skill = RSSSkill()
