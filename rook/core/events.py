"""
rook.core.events — Simple event bus
=====================================
Decouples modules. Skills emit events, services listen.

Usage:
    from rook.core.events import bus

    # Listen
    @bus.on("calendar.reminder")
    async def handle_reminder(data):
        await send_telegram(f"Reminder: {data['title']}")

    # Emit
    await bus.emit("calendar.reminder", {"title": "Standup", "minutes": 15})
"""

import asyncio
import logging
from collections import defaultdict
from typing import Callable, Any

logger = logging.getLogger(__name__)


class EventBus:
    """Async event bus with wildcard support."""

    def __init__(self):
        self._handlers: dict[str, list[Callable]] = defaultdict(list)

    def on(self, event: str):
        """Decorator to register an event handler."""
        def decorator(func: Callable):
            self._handlers[event].append(func)
            logger.debug(f"Event handler registered: {event} -> {func.__name__}")
            return func
        return decorator

    def subscribe(self, event: str, handler: Callable):
        """Programmatic subscription."""
        self._handlers[event].append(handler)

    def unsubscribe(self, event: str, handler: Callable):
        """Remove a handler."""
        if handler in self._handlers[event]:
            self._handlers[event].remove(handler)

    async def emit(self, event: str, data: Any = None):
        """Emit an event. All matching handlers are called."""
        handlers = self._handlers.get(event, [])

        # Wildcard: "calendar.*" matches "calendar.reminder"
        prefix = event.rsplit(".", 1)[0] + ".*" if "." in event else None
        if prefix:
            handlers = handlers + self._handlers.get(prefix, [])

        if not handlers:
            logger.debug(f"Event '{event}' emitted with no handlers")
            return

        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
            except Exception as e:
                logger.error(f"Event handler error [{event}] {handler.__name__}: {e}")

    def list_events(self) -> list[str]:
        """List all registered event types."""
        return sorted(self._handlers.keys())


# Singleton
bus = EventBus()
