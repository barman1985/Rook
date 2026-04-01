"""
rook.services.scheduler — Proactive scheduling
=================================================
Morning briefing, calendar reminders, evening summary.
Runs in background via APScheduler.

Usage:
    from rook.services.scheduler import start_scheduler
    start_scheduler()
"""

import logging
from datetime import datetime

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from rook.core.config import cfg
from rook.core.events import bus

logger = logging.getLogger(__name__)

_scheduler = None


def start_scheduler():
    """Start the proactive scheduler."""
    global _scheduler

    tz = pytz.timezone(cfg.timezone)
    _scheduler = AsyncIOScheduler(timezone=tz)

    # Morning briefing — weekdays at 7:00
    _scheduler.add_job(
        _morning_briefing,
        CronTrigger(hour=7, minute=0, day_of_week="mon-fri"),
        id="morning_briefing",
        name="Morning briefing",
    )

    # Evening summary — every day at 21:00
    _scheduler.add_job(
        _evening_summary,
        CronTrigger(hour=21, minute=0),
        id="evening_summary",
        name="Evening summary",
    )

    # Calendar reminders — every 15 minutes
    _scheduler.add_job(
        _calendar_reminders,
        IntervalTrigger(minutes=15),
        id="calendar_reminders",
        name="Calendar reminders",
    )

    # Heartbeat — every 60 minutes during active hours (7:00-22:00)
    _scheduler.add_job(
        _heartbeat,
        CronTrigger(minute=30, hour="7-21"),  # :30 past each hour, 7:30-21:30
        id="heartbeat",
        name="Heartbeat",
    )

    # Discovery — 4× daily (6:00, 10:00, 14:00, 18:00)
    _scheduler.add_job(
        _run_discovery,
        CronTrigger(hour="6,10,14,18", minute=0),
        id="discovery",
        name="Proactive discovery",
    )

    # Emotional consolidation — once daily at 23:00
    _scheduler.add_job(
        _consolidate_emotions,
        CronTrigger(hour=23, minute=0),
        id="emotional_consolidation",
        name="Emotional consolidation",
    )

    _scheduler.start()
    logger.info(f"Scheduler started (TZ: {cfg.timezone})")


async def _morning_briefing():
    """Generate and send morning briefing."""
    logger.info("Generating morning briefing")
    parts = []

    now = datetime.now(pytz.timezone(cfg.timezone))
    parts.append(f"☀️ Good morning! It's {now.strftime('%A, %B %d')}.")

    # Calendar
    if cfg.google_enabled:
        try:
            from rook.skills.builtin.calendar_skill import _get_calendar_service, _format_event
            service, err = _get_calendar_service()
            if service and not err:
                time_min = now.replace(hour=0, minute=0).isoformat()
                time_max = now.replace(hour=23, minute=59).isoformat()
                result = service.events().list(
                    calendarId="primary", timeMin=time_min, timeMax=time_max,
                    singleEvents=True, orderBy="startTime", maxResults=10,
                ).execute()
                events = result.get("items", [])
                if events:
                    parts.append(f"\n📅 Today's schedule ({len(events)} events):")
                    for ev in events:
                        parts.append(_format_event(ev))
                else:
                    parts.append("\n📅 No events today — clear schedule!")
        except Exception as e:
            logger.error(f"Morning briefing calendar error: {e}")

    # Unread emails
    if cfg.google_enabled:
        try:
            from rook.skills.builtin.email_skill import _get_gmail_service
            service, err = _get_gmail_service()
            if service and not err:
                result = service.users().messages().list(
                    userId="me", q="is:unread", maxResults=5
                ).execute()
                count = result.get("resultSizeEstimate", 0)
                if count > 0:
                    parts.append(f"\n📧 {count} unread email{'s' if count > 1 else ''}.")
                else:
                    parts.append("\n📧 Inbox zero!")
        except Exception as e:
            logger.error(f"Morning briefing email error: {e}")

    # Medications
    try:
        from rook.skills.builtin.medications_skill import skill as meds_skill
        stock = meds_skill.get_stock()
        if "⚠️" in stock:
            parts.append(f"\n💊 {stock}")
    except Exception:
        pass

    briefing = "\n".join(parts)
    await bus.emit("notification.send", {"text": briefing})


async def _evening_summary():
    """Generate evening summary."""
    logger.info("Generating evening summary")
    parts = []

    now = datetime.now(pytz.timezone(cfg.timezone))
    parts.append(f"🌙 Evening summary for {now.strftime('%A, %B %d')}.")

    # Tomorrow's calendar
    if cfg.google_enabled:
        try:
            from rook.skills.builtin.calendar_skill import _get_calendar_service, _format_event
            service, err = _get_calendar_service()
            if service and not err:
                from datetime import timedelta
                tomorrow = now + timedelta(days=1)
                time_min = tomorrow.replace(hour=0, minute=0).isoformat()
                time_max = tomorrow.replace(hour=23, minute=59).isoformat()
                result = service.events().list(
                    calendarId="primary", timeMin=time_min, timeMax=time_max,
                    singleEvents=True, orderBy="startTime", maxResults=10,
                ).execute()
                events = result.get("items", [])
                if events:
                    parts.append(f"\n📅 Tomorrow ({len(events)} events):")
                    for ev in events:
                        parts.append(_format_event(ev))
                else:
                    parts.append("\n📅 Tomorrow is clear.")
        except Exception as e:
            logger.error(f"Evening summary error: {e}")

    parts.append("\nGood night! 🌙")
    await bus.emit("notification.send", {"text": "\n".join(parts)})


async def _calendar_reminders():
    """Check for upcoming events and send reminders."""
    if not cfg.google_enabled:
        return

    try:
        from rook.skills.builtin.calendar_skill import _get_calendar_service
        from datetime import timedelta

        service, err = _get_calendar_service()
        if err:
            return

        tz = pytz.timezone(cfg.timezone)
        now = datetime.now(tz)
        window_start = now + timedelta(minutes=10)
        window_end = now + timedelta(minutes=25)

        result = service.events().list(
            calendarId="primary",
            timeMin=window_start.isoformat(),
            timeMax=window_end.isoformat(),
            singleEvents=True, orderBy="startTime",
        ).execute()

        for ev in result.get("items", []):
            title = ev.get("summary", "(no title)")
            start = ev.get("start", {}).get("dateTime", "")
            if start:
                start_dt = datetime.fromisoformat(start)
                mins = int((start_dt - now).total_seconds() / 60)
                await bus.emit("notification.send", {
                    "text": f"🔔 Reminder: {title} in {mins} minutes"
                })

    except Exception as e:
        logger.debug(f"Calendar reminder check: {e}")


async def _heartbeat():
    """
    Proactive heartbeat — reads HEARTBEAT.md checklist, asks LLM
    to evaluate whether anything needs attention, sends notification
    only if something does. Silent otherwise.
    """
    logger.debug("Heartbeat tick")

    # Load checklist
    from pathlib import Path
    heartbeat_path = Path(cfg.base_dir) / "HEARTBEAT.md"
    if not heartbeat_path.exists():
        return

    checklist = heartbeat_path.read_text(errors="replace")

    # Gather context for LLM
    context_parts = []

    # Calendar: next 2 hours
    if cfg.google_enabled:
        try:
            from rook.skills.builtin.calendar_skill import _get_calendar_service, _format_event
            from datetime import timedelta
            service, err = _get_calendar_service()
            if service and not err:
                tz = pytz.timezone(cfg.timezone)
                now = datetime.now(tz)
                result = service.events().list(
                    calendarId="primary",
                    timeMin=now.isoformat(),
                    timeMax=(now + timedelta(hours=2)).isoformat(),
                    singleEvents=True, orderBy="startTime", maxResults=5,
                ).execute()
                events = result.get("items", [])
                if events:
                    context_parts.append("Upcoming events (next 2h):")
                    for ev in events:
                        context_parts.append(f"  {_format_event(ev)}")
                else:
                    context_parts.append("No events in next 2 hours.")
        except Exception as e:
            logger.debug(f"Heartbeat calendar: {e}")

    # Unread emails
    if cfg.google_enabled:
        try:
            from rook.skills.builtin.email_skill import _get_gmail_service
            service, err = _get_gmail_service()
            if service and not err:
                result = service.users().messages().list(
                    userId="me", q="is:unread", maxResults=3
                ).execute()
                count = result.get("resultSizeEstimate", 0)
                context_parts.append(f"Unread emails: {count}")
        except Exception:
            pass

    if not context_parts:
        context_parts.append("No data sources available for checks.")

    context = "\n".join(context_parts)

    # Ask LLM to evaluate
    try:
        from rook.core.llm import llm
        prompt = (
            f"You are Rook, running a periodic heartbeat check.\n\n"
            f"CHECKLIST:\n{checklist}\n\n"
            f"CURRENT STATE:\n{context}\n\n"
            f"Based on the checklist and current state, does anything need the user's attention RIGHT NOW?\n"
            f"If YES: respond with a SHORT notification message (max 2 sentences).\n"
            f"If NO: respond with exactly 'HEARTBEAT_OK' and nothing else.\n"
            f"Be conservative — only notify if it's genuinely important."
        )

        response = await llm.chat(prompt, max_tokens=200)
        response = response.strip()

        if response and response != "HEARTBEAT_OK":
            logger.info(f"Heartbeat notification: {response[:100]}")
            await bus.emit("notification.send", {"text": f"💓 {response}"})
        else:
            logger.debug("Heartbeat: OK, nothing to report")

    except Exception as e:
        logger.error(f"Heartbeat LLM error: {e}")


async def _run_discovery():
    """Run proactive content discovery."""
    logger.debug("Running discovery scan")
    try:
        from rook.services.discovery import discovery
        await discovery.run_discovery()
    except Exception as e:
        logger.error(f"Discovery error: {e}")


async def _consolidate_emotions():
    """Consolidate daily emotional session into imprint."""
    logger.debug("Consolidating emotional session")
    try:
        from rook.core.emotional_memory import emotions
        result = emotions.consolidate_session()
        if result:
            logger.info(f"Emotional imprint #{result} created")
    except Exception as e:
        logger.error(f"Emotional consolidation error: {e}")
