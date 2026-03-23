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
from rook.core.db import execute_write, execute, get_message_count, get_recent_messages, delete_old_messages, save_profile, get_profile
from rook.core.events import bus
from rook.core.llm import llm
from rook.router.orchestrator import handle as orchestrate
from rook.services.prompt import build_system_prompt

logger = logging.getLogger(__name__)

COMPACTION_THRESHOLD = 50
MESSAGES_KEEP = 20


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


async def _maybe_compact():
    """Summarize and delete old messages when threshold is reached."""
    total = get_message_count()
    if total < COMPACTION_THRESHOLD:
        return
    try:
        messages = get_recent_messages(total)
        to_summarize = messages[:-MESSAGES_KEEP]
        if not to_summarize:
            return

        existing_summary = get_profile("conversation_summary") or ""
        lines = [f"{'User' if m['role'] == 'user' else 'Rook'}: {m['content'][:300]}" for m in to_summarize]

        summary = await llm.chat(
            f"Create a concise summary of these conversations (max 500 words). "
            f"Focus on facts, preferences, decisions.\n\n"
            f"Existing summary:\n{existing_summary or '(none)'}\n\n"
            f"New conversations:\n" + "\n".join(lines),
            max_tokens=1000,
        )
        save_profile("conversation_summary", summary)
        deleted = delete_old_messages(keep_latest=MESSAGES_KEEP)
        logger.info(f"Compaction: summarized and deleted {deleted} messages")
    except Exception as e:
        logger.error(f"Compaction error: {e}")


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

        # Background compaction check
        await _maybe_compact()

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
        "Just send me a message and I'll help you manage your day.\n\n"
        "Commands:\n"
        "/status — system status\n"
        "/skills — list loaded skills\n"
        "/post_yes — approve pending tweet\n"
        "/post_no — reject pending tweet"
    )


async def handle_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """System status."""
    if not is_allowed(update.effective_user.id):
        return

    from rook.skills.loader import get_all_skills, get_all_tools
    from rook.core.memory import memory

    skills = get_all_skills()
    tools = get_all_tools()
    mem_count = memory.count()

    status = (
        f"\u265C Rook status\n\n"
        f"Skills: {len(skills)} loaded\n"
        f"Tools: {len(tools)} available\n"
        f"Memory: {mem_count} facts\n"
        f"Model: {cfg.main_model}\n"
        f"Features: {cfg.summary().split(chr(10))[1]}"
    )
    await update.message.reply_text(status)


async def handle_skills(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List loaded skills and their tools."""
    if not is_allowed(update.effective_user.id):
        return

    from rook.skills.loader import get_all_skills

    skills = get_all_skills()
    lines = ["\u265C Loaded skills:"]
    for name, skill in skills.items():
        tools = skill.get_tools()
        tool_names = ", ".join(t["name"] for t in tools)
        lines.append(f"\n  {name} v{skill.version} ({len(tools)} tools)")
        if tool_names:
            lines.append(f"    {tool_names}")

    await update.message.reply_text("\n".join(lines))


async def handle_post_yes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Approve pending tweet."""
    if not is_allowed(update.effective_user.id):
        return
    try:
        from rook.skills.builtin.x_posting_skill import skill as x_skill
        result = x_skill.approve_tweet()
        await update.message.reply_text(result)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def handle_post_no(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reject pending tweet."""
    if not is_allowed(update.effective_user.id):
        return
    try:
        from rook.skills.builtin.x_posting_skill import skill as x_skill
        result = x_skill.reject_tweet()
        await update.message.reply_text(result)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle voice messages — STT then process as text."""
    if not is_allowed(update.effective_user.id):
        return

    if not cfg.voice_enabled:
        await update.message.reply_text("Voice is not configured. See docs/voice-setup.md")
        return

    import tempfile
    import subprocess

    try:
        # Download voice file
        voice = update.message.voice or update.message.audio
        if not voice:
            return

        file = await context.bot.get_file(voice.file_id)

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp_path = tmp.name

        await file.download_to_drive(tmp_path)

        # Convert to WAV for whisper
        wav_path = tmp_path.replace(".ogg", ".wav")
        subprocess.run(
            ["ffmpeg", "-i", tmp_path, "-ar", "16000", "-ac", "1", wav_path, "-y"],
            capture_output=True, timeout=30,
        )

        # Transcribe with faster-whisper
        from faster_whisper import WhisperModel
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(wav_path, language="cs")
        text = " ".join(s.text for s in segments).strip()

        # Cleanup
        import os
        os.unlink(tmp_path)
        os.unlink(wav_path)

        if not text:
            await update.message.reply_text("Could not transcribe voice message.")
            return

        # Process as regular text message
        await update.message.reply_text(f"🎙️ {text}")
        update.message.text = text
        await handle_message(update, context)

    except ImportError:
        await update.message.reply_text("faster-whisper not installed. Run: pip install faster-whisper")
    except Exception as e:
        logger.error(f"Voice handler error: {e}")
        await update.message.reply_text(f"Voice processing error: {e}")


def create_app() -> Application:
    """Create and configure the Telegram bot application."""
    app = Application.builder().token(cfg.telegram_bot_token).build()

    # Commands
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("status", handle_status))
    app.add_handler(CommandHandler("skills", handle_skills))
    app.add_handler(CommandHandler("post_yes", handle_post_yes))
    app.add_handler(CommandHandler("post_no", handle_post_no))

    # Messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))

    return app
