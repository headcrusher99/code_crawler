"""Plugin Registry — lifecycle management for discovered plugins."""

from __future__ import annotations

import logging

from codecrawler.core.event_bus import EventBus
from codecrawler.core.registry import ServiceRegistry
from codecrawler.plugins.base import PluginBase

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Manages plugin lifecycle: register → activate → deactivate.

    Usage:
        registry = PluginRegistry(service_registry, event_bus)
        registry.register_all(plugins)
        registry.activate_all()
        # ... runtime ...
        registry.deactivate_all()
    """

    def __init__(
        self,
        service_registry: ServiceRegistry,
        event_bus: EventBus,
    ) -> None:
        self.service_registry = service_registry
        self.event_bus = event_bus
        self._plugins: dict[str, PluginBase] = {}
        self._active: set[str] = set()

    def register_all(self, plugins: list[PluginBase]) -> None:
        """Register all discovered plugins."""
        for plugin in plugins:
            name = plugin.manifest.name
            if name in self._plugins:
                logger.warning("Plugin '%s' already registered, skipping", name)
                continue

            try:
                plugin.register(self.service_registry)
                self._plugins[name] = plugin
                logger.info("Registered plugin: %s", plugin)
            except Exception:
                logger.exception("Failed to register plugin '%s'", name)

    def activate_all(self) -> None:
        """Activate all registered plugins."""
        for name, plugin in self._plugins.items():
            if name in self._active:
                continue

            try:
                plugin.activate(self.event_bus)
                self._active.add(name)
                logger.debug("Activated plugin: %s", name)
            except Exception:
                logger.exception("Failed to activate plugin '%s'", name)

    def deactivate_all(self) -> None:
        """Deactivate all active plugins."""
        for name in list(self._active):
            plugin = self._plugins[name]
            try:
                plugin.deactivate()
                self._active.discard(name)
                logger.debug("Deactivated plugin: %s", name)
            except Exception:
                logger.exception("Failed to deactivate plugin '%s'", name)

    def get_plugin(self, name: str) -> PluginBase | None:
        """Get a registered plugin by name."""
        return self._plugins.get(name)

    @property
    def registered_plugins(self) -> list[str]:
        """List names of all registered plugins."""
        return sorted(self._plugins.keys())

    @property
    def active_plugins(self) -> list[str]:
        """List names of all active plugins."""
        return sorted(self._active)
