"""Plugin Base — abstract base class and manifest for all plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PluginManifest:
    """Metadata describing a plugin."""

    name: str
    version: str
    description: str
    author: str
    plugin_type: str  # "crawler", "analyzer", "intelligence", "ui", "storage"
    dependencies: list[str] = field(default_factory=list)


class PluginBase(ABC):
    """Abstract base class for all Code Crawler plugins.

    Every plugin must implement:
    - manifest: Returns plugin metadata
    - register(): Called on discovery to register services
    - activate(): Called on startup to subscribe to events
    - deactivate(): Called on shutdown for cleanup
    """

    @property
    @abstractmethod
    def manifest(self) -> PluginManifest:
        """Return the plugin's manifest metadata."""

    def register(self, registry) -> None:
        """Called when the plugin is discovered.

        Register services, crawlers, or other components with the
        ServiceRegistry here.

        Args:
            registry: The ServiceRegistry instance.
        """

    def activate(self, event_bus) -> None:
        """Called when the plugin is activated.

        Subscribe to events on the EventBus here.

        Args:
            event_bus: The EventBus instance.
        """

    def deactivate(self) -> None:
        """Called on shutdown. Clean up resources here."""

    def __repr__(self) -> str:
        m = self.manifest
        return f"<Plugin '{m.name}' v{m.version} [{m.plugin_type}]>"
