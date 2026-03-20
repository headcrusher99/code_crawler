"""Shell Crawler — Shell script parser."""

from __future__ import annotations

import logging
import re

from codecrawler.core.types import (
    CallEdge,
    FileInfo,
    FunctionDef,
    ParseResult,
    VariableDef,
)
from codecrawler.crawlers.base import BaseCrawler
from codecrawler.plugins.base import PluginBase, PluginManifest

logger = logging.getLogger(__name__)

# Regex patterns for shell script elements
FUNC_PATTERN = re.compile(
    r"^(?:function\s+)?(\w+)\s*\(\s*\)\s*\{",
    re.MULTILINE,
)
VAR_PATTERN = re.compile(r"^(\w+)=(.*)$", re.MULTILINE)
SOURCE_PATTERN = re.compile(r"^\s*(?:\.|source)\s+(.+)$", re.MULTILINE)


class ShellCrawler(BaseCrawler):
    """Shell script parser using regex-based extraction."""

    @property
    def name(self) -> str:
        return "Shell Crawler"

    @property
    def supported_languages(self) -> list[str]:
        return ["shell"]

    def parse(self, file_info: FileInfo) -> ParseResult:
        """Parse a shell script and extract functions, variables, and sourced files."""
        logger.debug("Parsing shell script: %s", file_info.path)

        try:
            source = file_info.path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            logger.error("Could not read %s: %s", file_info.path, e)
            return ParseResult(file_info=file_info)

        functions = self._extract_functions(source)
        variables = self._extract_variables(source)
        calls = self._extract_calls(source, functions)

        return ParseResult(
            file_info=file_info,
            functions=functions,
            variables=variables,
            calls=calls,
        )

    def _extract_functions(self, source: str) -> list[FunctionDef]:
        """Extract shell function definitions."""
        functions = []
        for match in FUNC_PATTERN.finditer(source):
            name = match.group(1)
            line_num = source[:match.start()].count("\n") + 1

            # Find the matching closing brace
            brace_count = 1
            pos = match.end()
            while pos < len(source) and brace_count > 0:
                if source[pos] == "{":
                    brace_count += 1
                elif source[pos] == "}":
                    brace_count -= 1
                pos += 1
            end_line = source[:pos].count("\n") + 1

            functions.append(FunctionDef(
                name=name,
                signature=f"{name}()",
                start_line=line_num,
                end_line=end_line,
            ))
        return functions

    def _extract_variables(self, source: str) -> list[VariableDef]:
        """Extract global variable assignments."""
        variables = []
        for match in VAR_PATTERN.finditer(source):
            name = match.group(1)
            if name.startswith("_") or name in ("PATH", "HOME", "SHELL"):
                continue
            line_num = source[:match.start()].count("\n") + 1
            variables.append(VariableDef(
                name=name,
                is_global=True,
                line=line_num,
            ))
        return variables

    def _extract_calls(self, source: str, functions: list[FunctionDef]) -> list[CallEdge]:
        """Extract function calls (calls to locally defined functions)."""
        func_names = {f.name for f in functions}
        calls = []
        for i, line in enumerate(source.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                continue
            # Check if any known function name appears as a command
            first_word = stripped.split()[0] if stripped.split() else ""
            if first_word in func_names:
                calls.append(CallEdge(caller="", callee=first_word, call_site_line=i))
        return calls


class ShellCrawlerPlugin(PluginBase):
    """Plugin wrapper for the Shell script crawler."""

    @property
    def manifest(self) -> PluginManifest:
        return PluginManifest(
            name="shell_crawler",
            version="4.0.0",
            description="Shell script parser",
            author="Code Crawler Team",
            plugin_type="crawler",
        )

    def register(self, registry) -> None:
        registry.register(BaseCrawler, ShellCrawler())

    def activate(self, event_bus) -> None:
        pass
