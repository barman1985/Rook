"""
Built-in skill: X (Twitter) posting
======================================
Posts to X with Telegram approval flow.
Rook generates tweet → sends preview to Telegram → user approves → Rook posts.

Setup:
    pip install tweepy
    Add to .env:
        X_API_KEY=...
        X_API_SECRET=...
        X_ACCESS_TOKEN=...
        X_ACCESS_TOKEN_SECRET=...

Usage (in Telegram):
    "Rook, draft a tweet about our latest release"
    → Rook generates draft, asks for approval
    → User replies /post_yes or /post_no
    → Rook posts (or discards)
"""

import logging
import os
from datetime import datetime

from rook.skills.base import Skill, tool
from rook.core.db import execute, execute_write

logger = logging.getLogger(__name__)

# ── Pending tweets storage ──

def _init_tweets_table():
    """Create pending_tweets table if needed."""
    from rook.core.db import get_db
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pending_tweets (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                content     TEXT NOT NULL,
                status      TEXT DEFAULT 'pending',
                created_at  TEXT DEFAULT (datetime('now')),
                posted_at   TEXT,
                tweet_id    TEXT
            )
        """)
        conn.commit()


def _get_x_client():
    """Create authenticated X API client."""
    try:
        import tweepy
    except ImportError:
        return None, "tweepy not installed. Run: pip install tweepy"

    api_key = os.environ.get("X_API_KEY", "")
    api_secret = os.environ.get("X_API_SECRET", "")
    access_token = os.environ.get("X_ACCESS_TOKEN", "")
    access_secret = os.environ.get("X_ACCESS_TOKEN_SECRET", "")

    if not all([api_key, api_secret, access_token, access_secret]):
        return None, "X API credentials missing. Add X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET to .env"

    client = tweepy.Client(
        consumer_key=api_key,
        consumer_secret=api_secret,
        access_token=access_token,
        access_token_secret=access_secret,
    )
    return client, None


class XPostingSkill(Skill):
    name = "x_posting"
    description = "Draft and post tweets to X (Twitter) with approval"
    version = "1.0"

    def __init__(self):
        super().__init__()
        # Check if X credentials are available
        self.enabled = bool(os.environ.get("X_API_KEY"))
        if self.enabled:
            _init_tweets_table()

    @tool(
        "draft_tweet",
        "Create a tweet draft for X. The tweet will be shown to the user for approval before posting.",
        {"type": "object", "properties": {
            "content": {"type": "string", "description": "Tweet text (max 280 characters)"},
        }, "required": ["content"]}
    )
    def draft_tweet(self, content: str) -> str:
        """Save tweet as pending and ask for approval."""
        # Validate length
        if len(content) > 280:
            return f"Tweet is too long ({len(content)}/280 chars). Shorten it."

        if len(content) < 5:
            return "Tweet is too short. Write something meaningful."

        # Save to pending
        _init_tweets_table()
        tweet_id = execute_write(
            "INSERT INTO pending_tweets (content) VALUES (?)",
            (content,)
        )

        return (
            f"Tweet draft saved (#{tweet_id}):\n\n"
            f"\"{content}\"\n\n"
            f"({len(content)}/280 chars)\n\n"
            f"Reply /post_yes to post or /post_no to discard."
        )

    @tool(
        "approve_tweet",
        "Post the latest pending tweet to X",
        {"type": "object", "properties": {}, "required": []}
    )
    def approve_tweet(self) -> str:
        """Post the latest pending tweet."""
        _init_tweets_table()

        # Get latest pending tweet
        rows = execute(
            "SELECT id, content FROM pending_tweets WHERE status = 'pending' ORDER BY id DESC LIMIT 1"
        )
        if not rows:
            return "No pending tweets to post."

        tweet = rows[0]
        content = tweet["content"]
        tweet_db_id = tweet["id"]

        # Post to X
        client, error = _get_x_client()
        if error:
            return f"Cannot post: {error}"

        try:
            response = client.create_tweet(text=content)
            x_tweet_id = response.data["id"]

            # Update status
            execute_write(
                "UPDATE pending_tweets SET status = 'posted', posted_at = datetime('now'), tweet_id = ? WHERE id = ?",
                (str(x_tweet_id), tweet_db_id)
            )

            logger.info(f"Tweet posted: {x_tweet_id}")
            return f"Posted to X!\n\nhttps://x.com/i/status/{x_tweet_id}"

        except Exception as e:
            execute_write(
                "UPDATE pending_tweets SET status = 'failed' WHERE id = ?",
                (tweet_db_id,)
            )
            logger.error(f"Tweet posting failed: {e}")
            return f"Failed to post: {e}"

    @tool(
        "reject_tweet",
        "Discard the latest pending tweet",
        {"type": "object", "properties": {}, "required": []}
    )
    def reject_tweet(self) -> str:
        """Discard pending tweet."""
        _init_tweets_table()
        rows = execute(
            "SELECT id, content FROM pending_tweets WHERE status = 'pending' ORDER BY id DESC LIMIT 1"
        )
        if not rows:
            return "No pending tweets to discard."

        execute_write(
            "UPDATE pending_tweets SET status = 'rejected' WHERE id = ?",
            (rows[0]["id"],)
        )
        return "Tweet discarded."

    @tool(
        "list_posted_tweets",
        "Show recent tweets posted through Rook",
        {"type": "object", "properties": {
            "limit": {"type": "integer", "description": "Number of tweets to show (default 5)"},
        }, "required": []}
    )
    def list_posted_tweets(self, limit: int = 5) -> str:
        """List recently posted tweets."""
        _init_tweets_table()
        rows = execute(
            "SELECT content, status, posted_at, tweet_id FROM pending_tweets ORDER BY id DESC LIMIT ?",
            (limit,)
        )
        if not rows:
            return "No tweets in history."

        lines = ["Recent tweets:"]
        for r in rows:
            status_icon = {"posted": "✅", "pending": "⏳", "rejected": "❌", "failed": "💥"}.get(r["status"], "?")
            posted = f" ({r['posted_at'][:16]})" if r["posted_at"] else ""
            link = f"\nhttps://x.com/i/status/{r['tweet_id']}" if r["tweet_id"] else ""
            lines.append(f"{status_icon} \"{r['content'][:80]}{'...' if len(r['content']) > 80 else ''}\"{posted}{link}")

        return "\n\n".join(lines)

    @tool(
        "generate_tweet",
        "Ask Rook to generate a tweet about a topic. Returns a draft for approval.",
        {"type": "object", "properties": {
            "topic": {"type": "string", "description": "What the tweet should be about"},
            "style": {"type": "string", "description": "Tone: professional, casual, witty, technical (default: professional)"},
        }, "required": ["topic"]}
    )
    async def generate_tweet(self, topic: str, style: str = "professional") -> str:
        """Generate a tweet using LLM and save as draft."""
        from rook.core.llm import llm

        prompt = f"""Write a single tweet (max 270 chars to leave room for edits) about: {topic}

Style: {style}
Account context: Rook is an open-source AI personal assistant. The account shares updates, AI insights, and productivity tips.

Rules:
- Max 270 characters
- No hashtag spam (max 2 relevant hashtags)
- Sound human, not corporate
- Be specific and valuable, not generic

Respond with ONLY the tweet text, nothing else."""

        try:
            tweet_text = await llm.chat(prompt, max_tokens=200)
            tweet_text = tweet_text.strip().strip('"')

            if len(tweet_text) > 280:
                tweet_text = tweet_text[:277] + "..."

            return self.draft_tweet(tweet_text)
        except Exception as e:
            return f"Failed to generate tweet: {e}"


skill = XPostingSkill()
