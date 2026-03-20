"""
rook.services.notifications — Send proactive messages
=======================================================
Listens on event bus, sends to Telegram.
"""

import logging

import httpx

from rook.core.config import cfg
from rook.core.events import bus

logger = logging.getLogger(__name__)

API = f"https://api.telegram.org/bot{cfg.telegram_bot_token}"


@bus.on("notification.send")
async def send_notification(data: dict):
    """Send a notification message to the user via Telegram."""
    text = data.get("text", "")
    if not text:
        return

    try:
        async with httpx.AsyncClient() as client:
            # Chunk if needed
            chunks = [text[i:i + 4096] for i in range(0, len(text), 4096)]
            for chunk in chunks:
                await client.post(f"{API}/sendMessage", json={
                    "chat_id": cfg.telegram_chat_id,
                    "text": chunk,
                })
        logger.debug(f"Notification sent ({len(text)} chars)")
    except Exception as e:
        logger.error(f"Notification failed: {e}")
