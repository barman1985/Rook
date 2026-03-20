"""
Built-in skill: Google Calendar
=================================
Create, search, edit, delete calendar events.

Setup: Google OAuth credentials (see docs/google-setup.md)
"""

import os
import logging
from datetime import datetime, timedelta

import pytz

from rook.skills.base import Skill, tool
from rook.core.config import cfg

logger = logging.getLogger(__name__)


def _get_calendar_service():
    """Get authenticated Google Calendar service."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    token_path = os.path.join(cfg.base_dir, "token.json")
    creds_path = cfg.google_credentials_path

    if not os.path.exists(token_path):
        return None, "token.json not found. Run OAuth flow first."

    creds = Credentials.from_authorized_user_file(token_path)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return build("calendar", "v3", credentials=creds), None


def _format_event(ev: dict) -> str:
    """Format a single event for display."""
    start = ev.get("start", {})
    dt = start.get("dateTime", start.get("date", ""))
    title = ev.get("summary", "(no title)")
    loc = ev.get("location", "")
    eid = ev.get("id", "")
    line = f"  • {dt[:16]} — {title}"
    if loc:
        line += f" ({loc})"
    if eid:
        line += f"\n    event_id: {eid}"
    return line


class CalendarSkill(Skill):
    name = "calendar"
    description = "Google Calendar — create, search, edit, delete events"
    version = "1.0"

    def __init__(self):
        super().__init__()
        self.enabled = cfg.google_enabled

    @tool(
        "search_calendar",
        "Search calendar events by keyword",
        {"type": "object", "properties": {
            "query": {"type": "string", "description": "Search term"},
        }, "required": ["query"]}
    )
    def search_calendar(self, query: str) -> str:
        service, err = _get_calendar_service()
        if err:
            return err

        tz = pytz.timezone(cfg.timezone)
        now = datetime.now(tz)
        time_min = (now - timedelta(days=30)).isoformat()
        time_max = (now + timedelta(days=30)).isoformat()

        result = service.events().list(
            calendarId="primary", q=query,
            timeMin=time_min, timeMax=time_max,
            singleEvents=True, orderBy="startTime", maxResults=10,
        ).execute()

        events = result.get("items", [])
        if not events:
            return f"No events found for: {query}"

        lines = [f"Calendar results for '{query}':"]
        for ev in events:
            lines.append(_format_event(ev))
        return "\n".join(lines)

    @tool(
        "create_calendar_event",
        "Create a new calendar event",
        {"type": "object", "properties": {
            "title": {"type": "string", "description": "Event title"},
            "start": {"type": "string", "description": "Start time (ISO format or natural like '2026-03-21 14:00')"},
            "end": {"type": "string", "description": "End time (ISO format, optional — defaults to 1 hour after start)"},
            "description": {"type": "string", "description": "Event description (optional)"},
            "location": {"type": "string", "description": "Location (optional)"},
        }, "required": ["title", "start"]}
    )
    def create_event(self, title: str, start: str, end: str = "", description: str = "", location: str = "") -> str:
        service, err = _get_calendar_service()
        if err:
            return err

        tz = cfg.timezone
        start_dt = _parse_datetime(start, tz)
        if not start_dt:
            return f"Cannot parse start time: {start}"

        if end:
            end_dt = _parse_datetime(end, tz)
        else:
            end_dt = start_dt + timedelta(hours=1)

        if not end_dt:
            return f"Cannot parse end time: {end}"

        event = {
            "summary": title,
            "start": {"dateTime": start_dt.isoformat(), "timeZone": tz},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": tz},
        }
        if description:
            event["description"] = description
        if location:
            event["location"] = location

        created = service.events().insert(calendarId="primary", body=event).execute()
        return f"Event created: {title} at {start_dt.strftime('%Y-%m-%d %H:%M')}\nevent_id: {created['id']}"

    @tool(
        "update_calendar_event",
        "Update an existing calendar event",
        {"type": "object", "properties": {
            "event_id": {"type": "string", "description": "Event ID"},
            "title": {"type": "string", "description": "New title (optional)"},
            "start": {"type": "string", "description": "New start time (optional)"},
            "end": {"type": "string", "description": "New end time (optional)"},
            "description": {"type": "string", "description": "New description (optional)"},
            "location": {"type": "string", "description": "New location (optional)"},
        }, "required": ["event_id"]}
    )
    def update_event(self, event_id: str, title: str = "", start: str = "", end: str = "", description: str = "", location: str = "") -> str:
        service, err = _get_calendar_service()
        if err:
            return err

        try:
            event = service.events().get(calendarId="primary", eventId=event_id).execute()
        except Exception as e:
            return f"Event not found: {e}"

        tz = cfg.timezone
        if title:
            event["summary"] = title
        if start:
            dt = _parse_datetime(start, tz)
            if dt:
                event["start"] = {"dateTime": dt.isoformat(), "timeZone": tz}
        if end:
            dt = _parse_datetime(end, tz)
            if dt:
                event["end"] = {"dateTime": dt.isoformat(), "timeZone": tz}
        if description:
            event["description"] = description
        if location:
            event["location"] = location

        updated = service.events().update(calendarId="primary", eventId=event_id, body=event).execute()
        return f"Event updated: {updated.get('summary', '')}"

    @tool(
        "delete_calendar_event",
        "Delete a calendar event by ID",
        {"type": "object", "properties": {
            "event_id": {"type": "string", "description": "Event ID to delete"},
        }, "required": ["event_id"]}
    )
    def delete_event(self, event_id: str) -> str:
        service, err = _get_calendar_service()
        if err:
            return err

        try:
            service.events().delete(calendarId="primary", eventId=event_id).execute()
            return f"Event {event_id} deleted."
        except Exception as e:
            return f"Failed to delete: {e}"


def _parse_datetime(value: str, tz_name: str):
    """Parse datetime string to timezone-aware datetime."""
    tz = pytz.timezone(tz_name)
    for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"]:
        try:
            dt = datetime.strptime(value, fmt)
            return tz.localize(dt)
        except ValueError:
            continue
    return None


skill = CalendarSkill()
