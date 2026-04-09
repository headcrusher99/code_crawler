"""Crawlers — language-specific parsers implementing BaseCrawler.

All crawlers are registered here for auto-discovery by the pipeline.
"""

from codecrawler.crawlers.base import BaseCrawler
from codecrawler.crawlers.c_crawler import CCrawler
from codecrawler.crawlers.python_crawler import PythonCrawler
from codecrawler.crawlers.shell_crawler import ShellCrawler
from codecrawler.crawlers.dts_crawler import DTSCrawler
from codecrawler.crawlers.rust_crawler import RustCrawler
from codecrawler.crawlers.go_crawler import GoCrawler
from codecrawler.crawlers.bitbake_crawler import BitbakeCrawler

# Registry of all available crawlers (instantiated)
ALL_CRAWLERS: list[BaseCrawler] = [
    CCrawler(),
    PythonCrawler(),
    ShellCrawler(),
    DTSCrawler(),
    RustCrawler(),
    GoCrawler(),
    BitbakeCrawler(),
]

# Map language → crawler for fast lookup
CRAWLER_MAP: dict[str, BaseCrawler] = {}
for _crawler in ALL_CRAWLERS:
    for _lang in _crawler.supported_languages:
        CRAWLER_MAP[_lang] = _crawler


def get_crawler(language: str) -> BaseCrawler | None:
    """Get the crawler for a given language, or None if unsupported."""
    return CRAWLER_MAP.get(language)


__all__ = [
    "BaseCrawler",
    "CCrawler",
    "PythonCrawler",
    "ShellCrawler",
    "DTSCrawler",
    "RustCrawler",
    "GoCrawler",
    "BitbakeCrawler",
    "ALL_CRAWLERS",
    "CRAWLER_MAP",
    "get_crawler",
]
