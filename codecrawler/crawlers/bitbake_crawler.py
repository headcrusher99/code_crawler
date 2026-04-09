"""bitbake_crawler — Bitbake recipe (.bb/.bbappend/.bbclass) parser.

Extracts Bitbake recipe metadata, variable assignments, function
definitions (do_compile, do_install), and dependency relationships
from Yocto/OpenEmbedded build recipes.
"""

from __future__ import annotations

import logging
import re

from codecrawler.core.types import (
    CallEdge,
    FileInfo,
    FunctionDef,
    IncludeEdge,
    MacroDef,
    ParseResult,
    VariableDef,
)
from codecrawler.crawlers.base import BaseCrawler

logger = logging.getLogger(__name__)


class BitbakeCrawler(BaseCrawler):
    """Parser for Bitbake recipe files (.bb, .bbappend, .bbclass).

    Extracts:
      - Recipe variable assignments (SRC_URI, DEPENDS, RDEPENDS, etc.)
      - Task functions (do_compile, do_install, do_configure, etc.)
      - Inherit directives (as include edges)
      - Package dependencies (as call edges for the build graph)
      - DISTRO_FEATURES, MACHINE_FEATURES references
    """

    @property
    def name(self) -> str:
        return "Bitbake Recipe Crawler"

    @property
    def supported_languages(self) -> list[str]:
        return ["bitbake"]

    # ── Key Bitbake variables to track ───────────────────────────────
    _TRACKED_VARS = {
        "SUMMARY", "DESCRIPTION", "HOMEPAGE", "LICENSE", "LIC_FILES_CHKSUM",
        "SRC_URI", "SRCREV", "S", "B",
        "DEPENDS", "RDEPENDS", "RRECOMMENDS", "RPROVIDES", "RCONFLICTS",
        "PROVIDES", "BBCLASSEXTEND",
        "PACKAGECONFIG", "EXTRA_OECONF", "EXTRA_OECMAKE",
        "FILES", "PACKAGES",
        "COMPATIBLE_MACHINE", "MACHINE_FEATURES", "DISTRO_FEATURES",
        "IMAGE_INSTALL", "IMAGE_FEATURES",
        "inherit",
    }

    # ── Patterns ─────────────────────────────────────────────────────

    _VAR_ASSIGN = re.compile(
        r"""
        ^(?P<name>\w+)                      # Variable name
        \s*(?P<op>[?:+.]*=)                 # Assignment operator (=, ?=, +=, :=, .=)
        \s*(?P<value>.*)                    # Value (may span lines with \)
        """,
        re.VERBOSE | re.MULTILINE,
    )

    _TASK_PATTERN = re.compile(
        r"""
        (?:^|\n)                             # Start of line
        (?P<name>do_\w+|python\s+\w+)       # Task name
        \s*\(\)\s*\{                         # () {
        """,
        re.VERBOSE,
    )

    _PYTHON_TASK_PATTERN = re.compile(
        r"""
        python\s+(?P<name>\w+)\s*\(\)\s*\{
        """,
        re.VERBOSE,
    )

    _INHERIT_PATTERN = re.compile(r"inherit\s+(.+)")
    _REQUIRE_PATTERN = re.compile(r"require\s+(\S+)")
    _INCLUDE_PATTERN = re.compile(r"include\s+(\S+)")

    _DEPENDS_PATTERN = re.compile(r'DEPENDS\s*[+:]*=\s*"([^"]*)"')
    _RDEPENDS_PATTERN = re.compile(
        r'RDEPENDS[_:]?\$\{PN\}\s*[+:]*=\s*"([^"]*)"'
    )

    def parse(self, file_info: FileInfo) -> ParseResult:
        """Parse a Bitbake recipe file."""
        try:
            source = file_info.path.read_text(errors="ignore")
        except OSError:
            return ParseResult(file_info=file_info)

        lines = source.splitlines()
        file_path = str(file_info.path)

        functions = self._extract_tasks(source, lines)
        variables = self._extract_variables(source)
        macros = self._extract_config_refs(source)
        includes = self._extract_includes(source, file_path)
        calls = self._extract_dependency_edges(source)

        return ParseResult(
            file_info=file_info,
            functions=functions,
            variables=variables,
            macros=macros,
            calls=calls,
            includes=includes,
        )

    def _extract_tasks(
        self, source: str, lines: list[str]
    ) -> list[FunctionDef]:
        """Extract Bitbake task definitions (do_compile, do_install, etc.)."""
        tasks: list[FunctionDef] = []

        for match in self._TASK_PATTERN.finditer(source):
            name = match.group("name").strip()
            # Clean up python prefix
            if name.startswith("python "):
                name = name[7:]

            start_pos = match.start()
            start_line = source[:start_pos].count("\n") + 1
            end_line = self._find_closing_brace(lines, start_line - 1)

            body = "\n".join(lines[start_line - 1:end_line])
            complexity = 1 + body.count("if ") + body.count("for ") + body.count("while ")

            tasks.append(FunctionDef(
                name=name,
                signature=f"{name}()",
                start_line=start_line,
                end_line=end_line,
                complexity=complexity,
                is_exported=True,
                language="bitbake",
            ))

        return tasks

    def _extract_variables(self, source: str) -> list[VariableDef]:
        """Extract key variable assignments."""
        variables: list[VariableDef] = []

        for match in self._VAR_ASSIGN.finditer(source):
            name = match.group("name")
            if name in self._TRACKED_VARS or name.startswith("PACKAGECONFIG"):
                value = match.group("value").strip().strip('"')
                line = source[:match.start()].count("\n") + 1
                variables.append(VariableDef(
                    name=name,
                    var_type="string",
                    is_global=True,
                    scope="global",
                    line=line,
                ))

        return variables

    def _extract_config_refs(self, source: str) -> list[MacroDef]:
        """Extract references to DISTRO_FEATURES, MACHINE_FEATURES, etc."""
        macros: list[MacroDef] = []

        # Find DISTRO_FEATURES checks
        for match in re.finditer(
            r'bb\.utils\.contains\s*\(\s*["\'](\w+)["\']\s*,'
            r'\s*["\'](\w+)["\']',
            source,
        ):
            macros.append(MacroDef(
                name=f"{match.group(1)}:{match.group(2)}",
                value=match.group(2),
                is_config_guard=True,
            ))

        # Find PACKAGECONFIG options
        for match in re.finditer(
            r'PACKAGECONFIG\[(\w+)\]\s*=\s*"([^"]*)"',
            source,
        ):
            macros.append(MacroDef(
                name=f"PACKAGECONFIG:{match.group(1)}",
                value=match.group(2),
                is_config_guard=True,
            ))

        return macros

    def _extract_includes(
        self, source: str, file_path: str
    ) -> list[IncludeEdge]:
        """Extract inherit, require, and include directives."""
        includes: list[IncludeEdge] = []

        for match in self._INHERIT_PATTERN.finditer(source):
            for cls in match.group(1).split():
                cls = cls.strip()
                if cls:
                    includes.append(IncludeEdge(
                        source_path=file_path,
                        target_path=f"classes/{cls}.bbclass",
                    ))

        for pattern in (self._REQUIRE_PATTERN, self._INCLUDE_PATTERN):
            for match in pattern.finditer(source):
                path = match.group(1).strip()
                if path:
                    includes.append(IncludeEdge(
                        source_path=file_path,
                        target_path=path,
                    ))

        return includes

    def _extract_dependency_edges(self, source: str) -> list[CallEdge]:
        """Extract build/runtime dependency edges as call edges."""
        calls: list[CallEdge] = []
        file_recipe = "this_recipe"

        # Build dependencies (DEPENDS)
        for match in self._DEPENDS_PATTERN.finditer(source):
            for dep in match.group(1).split():
                dep = dep.strip()
                if dep and not dep.startswith("$"):
                    calls.append(CallEdge(
                        caller=file_recipe,
                        callee=dep,
                        call_site_line=source[:match.start()].count("\n") + 1,
                    ))

        return calls

    @staticmethod
    def _find_closing_brace(lines: list[str], start_idx: int) -> int:
        depth = 0
        for i in range(start_idx, len(lines)):
            depth += lines[i].count("{") - lines[i].count("}")
            if depth <= 0 and i > start_idx:
                return i + 1
        return min(start_idx + 1, len(lines))
