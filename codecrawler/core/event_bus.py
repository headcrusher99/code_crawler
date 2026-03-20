"""Event Bus — pub/sub inter-component communication."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable

logger = logging.getLogger(__name__)


class EventBus:
    """Central event bus for decoupled component communication.

    Components publish events (e.g., 'file.parsed') and other components
    subscribe handlers. This eliminates direct cross-boundary imports.

    Usage:
        bus = EventBus()
        bus.subscribe("file.parsed", my_handler)
        bus.publish("file.parsed", parse_result)
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable]] = defaultdict(list)
        self._async_handlers: dict[str, list[Callable]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: Callable) -> None:
        """Register a synchronous handler for an event type."""
        self._handlers[event_type].append(handler)
        logger.debug("Subscribed %s to '%s'", handler.__qualname__, event_type)

    def subscribe_async(self, event_type: str, handler: Callable) -> None:
        """Register an async handler for an event type."""
        self._async_handlers[event_type].append(handler)
        logger.debug("Subscribed async %s to '%s'", handler.__qualname__, event_type)

    def unsubscribe(self, event_type: str, handler: Callable) -> None:
        """Remove a handler from an event type."""
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)
        if handler in self._async_handlers[event_type]:
            self._async_handlers[event_type].remove(handler)

    def publish(self, event_type: str, payload: Any = None) -> None:
        """Publish an event synchronously to all subscribed handlers."""
        handlers = self._handlers.get(event_type, [])
        if not handlers:
            logger.debug("No handlers for event '%s'", event_type)
            return

        for handler in handlers:
            try:
                handler(payload)
            except Exception:
                logger.exception(
                    "Error in handler %s for event '%s'",
                    handler.__qualname__,
                    event_type,
                )

    async def publish_async(self, event_type: str, payload: Any = None) -> None:
        """Publish an event to all async handlers."""
        # Fire sync handlers first
        self.publish(event_type, payload)

        # Then fire async handlers
        async_handlers = self._async_handlers.get(event_type, [])
        tasks = []
        for handler in async_handlers:
            try:
                tasks.append(asyncio.create_task(handler(payload)))
            except Exception:
                logger.exception(
                    "Error creating task for async handler %s on '%s'",
                    handler.__qualname__,
                    event_type,
                )

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def clear(self) -> None:
        """Remove all handlers."""
        self._handlers.clear()
        self._async_handlers.clear()

    @property
    def registered_events(self) -> list[str]:
        """List all event types with at least one handler."""
        all_events = set(self._handlers.keys()) | set(self._async_handlers.keys())
        return sorted(all_events)
