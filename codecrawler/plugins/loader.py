"""Plugin Loader — discover plugins via entry points and filesystem."""

from __future__ import annotations

import importlib
import logging
from pathlib import Path

from codecrawler.plugins.base import PluginBase

logger = logging.getLogger(__name__)


def discover_plugins(search_paths: list[str] | None = None) -> list[PluginBase]:
    """Discover and instantiate all available plugins.

    Plugins are discovered via two mechanisms:
    1. Python entry points (group: codecrawler.plugins)
    2. Filesystem scanning in search_paths

    Args:
        search_paths: Additional directories to scan for plugin modules.

    Returns:
        List of instantiated PluginBase subclasses.
    """
    plugins: list[PluginBase] = []

    # Mechanism 1: Entry points
    plugins.extend(_discover_via_entry_points())

    # Mechanism 2: Filesystem
    if search_paths:
        for path in search_paths:
            plugins.extend(_discover_via_filesystem(Path(path)))

    # Deduplicate by plugin name
    seen = set()
    unique = []
    for plugin in plugins:
        name = plugin.manifest.name
        if name not in seen:
            seen.add(name)
            unique.append(plugin)

    logger.info("Discovered %d plugins: %s", len(unique), [p.manifest.name for p in unique])
    return unique


def _discover_via_entry_points() -> list[PluginBase]:
    """Discover plugins registered as Python entry points."""
    plugins = []

    try:
        from importlib.metadata import entry_points

        eps = entry_points()

        # Python 3.12+ returns a SelectableGroups or dict
        if hasattr(eps, "select"):
            cc_eps = eps.select(group="codecrawler.plugins")
        elif isinstance(eps, dict):
            cc_eps = eps.get("codecrawler.plugins", [])
        else:
            cc_eps = [ep for ep in eps if ep.group == "codecrawler.plugins"]

        for ep in cc_eps:
            try:
                plugin_class = ep.load()
                if isinstance(plugin_class, type) and issubclass(plugin_class, PluginBase):
                    plugins.append(plugin_class())
                    logger.debug("Loaded entry point plugin: %s", ep.name)
                elif isinstance(plugin_class, PluginBase):
                    plugins.append(plugin_class)
                    logger.debug("Loaded entry point plugin instance: %s", ep.name)
            except Exception:
                logger.exception("Failed to load entry point plugin: %s", ep.name)

    except Exception:
        logger.debug("Entry point discovery failed (package may not be installed)")

    return plugins


def _discover_via_filesystem(search_dir: Path) -> list[PluginBase]:
    """Discover plugins by scanning a directory for Python files."""
    plugins = []

    if not search_dir.is_dir():
        return plugins

    for py_file in search_dir.glob("*.py"):
        if py_file.name.startswith("_"):
            continue

        module_name = f"codecrawler_plugin_{py_file.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # Find PluginBase subclasses in the module
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, PluginBase)
                        and attr is not PluginBase
                    ):
                        plugins.append(attr())
                        logger.debug("Loaded filesystem plugin: %s from %s", attr_name, py_file)

        except Exception:
            logger.exception("Failed to load plugin from %s", py_file)

    return plugins


def load_builtin_plugins() -> list[PluginBase]:
    """Load the built-in plugins (crawlers and analyzers)."""
    plugins = []

    builtins = [
        "codecrawler.crawlers.c_crawler.CCrawlerPlugin",
        "codecrawler.crawlers.python_crawler.PythonCrawlerPlugin",
        "codecrawler.crawlers.shell_crawler.ShellCrawlerPlugin",
    ]

    for dotted_path in builtins:
        try:
            module_path, class_name = dotted_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            plugin_class = getattr(module, class_name)
            plugins.append(plugin_class())
            logger.debug("Loaded built-in plugin: %s", class_name)
        except Exception:
            logger.exception("Failed to load built-in plugin: %s", dotted_path)

    return plugins
