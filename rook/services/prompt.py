"""
rook.services.prompt — System prompt builder
==============================================
Builds the system prompt with context: SOUL.md, memory, features, time.
"""

import logging
from datetime import datetime
from pathlib import Path

from rook.core.config import cfg
from rook.core.memory import memory
from rook.skills.loader import get_all_skills

logger = logging.getLogger(__name__)

_soul_cache = None
_soul_mtime = 0


def _load_soul() -> str:
    """Load SOUL.md — cached, auto-reloads on file change."""
    global _soul_cache, _soul_mtime

    soul_path = Path(cfg.base_dir) / "SOUL.md"
    if not soul_path.exists():
        return ""

    try:
        mtime = soul_path.stat().st_mtime
        if mtime != _soul_mtime or _soul_cache is None:
            _soul_cache = soul_path.read_text(errors="replace").strip()
            _soul_mtime = mtime
            logger.debug("SOUL.md reloaded")
        return _soul_cache
    except Exception as e:
        logger.warning(f"SOUL.md read error: {e}")
        return ""


def build_system_prompt() -> str:
    """Build system prompt with dynamic context."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")

    # Feature list from loaded skills
    skills = get_all_skills()
    skill_list = ", ".join(skills.keys()) if skills else "none"

    # Memory context
    mem_count = memory.count()

    # Soul (user-editable personality)
    soul = _load_soul()

    if soul:
        prompt = f"""{soul}

---
Current time: {now}
Timezone: {cfg.timezone}
Active skills: {skill_list}
Memory: {mem_count} stored facts
"""
    else:
        # Fallback if no SOUL.md exists
        prompt = f"""You are Rook, a personal AI assistant.
You live in Telegram and help your user manage their day — calendar, email, tasks, reminders, and more.

Current time: {now}
Timezone: {cfg.timezone}
Active skills: {skill_list}
Memory: {mem_count} stored facts

Your personality:
- Strategic and efficient — every word earns its place
- Proactive — anticipate needs, don't just react
- Warm but concise — friendly, never verbose
- You speak the user's language (detect from their messages)

Rules:
- Use tools when they help. Don't guess what's on the calendar — check it.
- If you store something in memory, confirm briefly.
- For complex tasks, think step by step but keep the final answer short.
- If you can't do something, say so directly.
"""
    return prompt
