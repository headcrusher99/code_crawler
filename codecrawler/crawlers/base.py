"""BaseCrawler — abstract base class defining the universal parse contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from codecrawler.core.types import FileInfo, ParseResult


class BaseCrawler(ABC):
    """Abstract base class for all language crawlers.

    Every crawler must:
    1. Declare which languages it supports.
    2. Implement parse() returning a universal ParseResult DTO.

    Crawlers are registered as plugins and discovered via the ServiceRegistry.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for this crawler."""

    @property
    @abstractmethod
    def supported_languages(self) -> list[str]:
        """List of language identifiers this crawler handles (e.g., ['c', 'cpp'])."""

    @abstractmethod
    def parse(self, file_info: FileInfo) -> ParseResult:
        """Parse a file and return a universal ParseResult.

        Args:
            file_info: Metadata about the file to parse.

        Returns:
            ParseResult containing all extracted functions, structs,
            macros, variables, calls, and includes.
        """

    def can_parse(self, file_info: FileInfo) -> bool:
        """Check if this crawler can handle a given file."""
        return file_info.language in self.supported_languages

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} languages={self.supported_languages}>"
