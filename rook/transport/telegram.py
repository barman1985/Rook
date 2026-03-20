"""
rook.transport.telegram — Telegram bot interface
==================================================
Handles incoming messages, routes to orchestrator, sends replies.
"""

import os
import logging

from telegram import Update
from telegram.ext import (
    Application,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    filters,
)

from rook.core.config import cfg
from rook.core.db import execute_write, execute
from rook.core.events import bus
from rook.router.orchestrator import handle as orchestrate
from rook.services.prompt import build_system_prompt

logger = logging.getLogger(__name__)


def is_allowed(user_id: int) -> bool:
    """Check if user is authorized."""
    allowed = cfg.telegram_chat_id
    return str(user_id) == str(allowed)


def save_message(role: str, content: str):
    """Persist conversation message."""
    execute_write(
        "INSERT INTO messages (role, content) VALUES (?, ?)",
        (role, content)
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main message handler."""
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("Access denied.")
        return

    user_text = update.message.text
    if not user_text:
        return

    await update.message.chat.send_action("typing")
    save_message("user", user_text)

    # Emit event
    await bus.emit("message.received", {"text": user_text, "user_id": update.effective_user.id})

    # Build system prompt and orchestrate
    system = build_system_prompt()

    thinking = None
    try:
        thinking = await update.message.reply_text("\U0001f914")
    except Exception:
        pass

    try:
        reply = await orchestrate(user_text, system)
        save_message("assistant", reply)

        # Send reply (chunked if needed)
        if thinking:
            try:
                if len(reply) <= 4096:
                    await thinking.edit_text(reply)
                    return
            except Exception:
                pass
            try:
                await thinking.delete()
            except Exception:
                pass

        if len(reply) > 4096:
            for i in range(0, len(reply), 4096):
                await update.message.reply_text(reply[i:i + 4096])
        else:
            await update.message.reply_text(reply)

    except Exception as e:
        logger.error(f"Message handling error: {e}")
        if thinking:
            try:
                await thinking.edit_text(f"Error: {e}")
            except Exception:
                pass


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    await update.message.reply_text(
        "\u265C Welcome to Rook — your strategic AI advantage.\n\n"
        "Just send me a message and I'll help you manage your day."
    )


def create_app() -> Application:
    """Create and configure the Telegram bot application."""
    app = Application.builder().token(cfg.telegram_bot_token).build()

    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return app
