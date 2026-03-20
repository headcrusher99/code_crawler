"""Plugin system — discovery, loading, and lifecycle management."""

from codecrawler.plugins.base import PluginBase, PluginManifest
from codecrawler.plugins.loader import discover_plugins
from codecrawler.plugins.registry import PluginRegistry

__all__ = ["PluginBase", "PluginManifest", "PluginRegistry", "discover_plugins"]
