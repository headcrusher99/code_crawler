"""Service Registry — central component discovery and dependency injection."""

from __future__ import annotations

import logging
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ServiceRegistry:
    """Central registry for component discovery and dependency injection.

    Components register their public interfaces at startup. Other components
    request dependencies through the registry, never through direct imports.

    Usage:
        registry = ServiceRegistry()
        registry.register(DatabaseInterface, duckdb_impl)
        db = registry.get(DatabaseInterface)
    """

    def __init__(self) -> None:
        self._services: dict[type, list[Any]] = {}

    def register(self, interface: type[T], implementation: T) -> None:
        """Register an implementation for an interface type."""
        if interface not in self._services:
            self._services[interface] = []
        self._services[interface].append(implementation)
        logger.debug(
            "Registered %s for interface %s",
            type(implementation).__name__,
            interface.__name__,
        )

    def get(self, interface: type[T]) -> T:
        """Get the primary (first registered) implementation for an interface.

        Raises:
            KeyError: If no implementation is registered for the interface.
        """
        implementations = self._services.get(interface)
        if not implementations:
            raise KeyError(
                f"No implementation registered for {interface.__name__}. "
                f"Available: {[k.__name__ for k in self._services]}"
            )
        return implementations[0]

    def get_all(self, interface: type[T]) -> list[T]:
        """Get all implementations for an interface (e.g., all crawlers)."""
        return list(self._services.get(interface, []))

    def has(self, interface: type) -> bool:
        """Check if an implementation exists for an interface."""
        return bool(self._services.get(interface))

    def unregister(self, interface: type) -> None:
        """Remove all implementations for an interface."""
        self._services.pop(interface, None)

    def clear(self) -> None:
        """Remove all registrations."""
        self._services.clear()

    @property
    def registered_interfaces(self) -> list[str]:
        """List all registered interface names."""
        return sorted(k.__name__ for k in self._services)
