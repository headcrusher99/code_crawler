"""Cross-Language Linker — detect and resolve FFI call edges across languages.

Post-processing stage that runs after all crawlers have parsed their files.
Detects patterns like:
    • C → Python: PyObject_CallFunction("func_name", ...)
    • Python → C: ctypes.CDLL / cffi
    • C → Shell:  system("script.sh") / popen("script.sh")
    • Shell → C:  direct binary invocations
    • Python → Shell: subprocess.run(["script.sh"])
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from codecrawler.core.types import ParseResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ForeignCallHint:
    """A detected cross-language call that needs resolution."""

    source_file: str
    source_language: str
    caller_name: str
    target_name: str
    target_language: str
    call_line: int
    pattern: str  # Which FFI pattern matched


# ── Detection Patterns ──────────────────────────────────────────────

# C → Python FFI patterns
C_TO_PYTHON = [
    re.compile(r'PyObject_CallFunction\s*\(\s*\w+\s*,\s*"([^"]*)"'),
    re.compile(r'PyObject_CallMethod\s*\(\s*\w+\s*,\s*"(\w+)"'),
    re.compile(r'PyImport_ImportModule\s*\(\s*"([^"]*)"'),
    re.compile(r'Py_CompileString\s*\(\s*"([^"]*)"'),
]

# C → Shell patterns
C_TO_SHELL = [
    re.compile(r'system\s*\(\s*"([^"]*)"'),
    re.compile(r'popen\s*\(\s*"([^"]*)"'),
    re.compile(r'execl?p?\s*\(\s*"([^"]*)"'),
]

# Python → C patterns
PYTHON_TO_C = [
    re.compile(r'ctypes\.CDLL\s*\(\s*["\']([^"\']*)["\']'),
    re.compile(r'ctypes\.cdll\.LoadLibrary\s*\(\s*["\']([^"\']*)["\']'),
    re.compile(r'ffi\.dlopen\s*\(\s*["\']([^"\']*)["\']'),
    re.compile(r'from\s+cffi\s+import\s+FFI'),
]

# Python → Shell patterns
PYTHON_TO_SHELL = [
    re.compile(r'subprocess\.(?:run|call|Popen|check_output)\s*\(\s*\[?\s*["\']([^"\']*)["\']'),
    re.compile(r'os\.system\s*\(\s*["\']([^"\']*)["\']'),
    re.compile(r'os\.popen\s*\(\s*["\']([^"\']*)["\']'),
]

# Shell → binary (potential C program) patterns
SHELL_TO_BINARY = [
    re.compile(r'^\s*(/usr/(?:local/)?(?:s?bin)/\w+)', re.MULTILINE),
    re.compile(r'^\s*(\./\w+)', re.MULTILINE),
]


class CrossLanguageLinker:
    """Detects and records call edges that cross language boundaries.

    Usage:
        linker = CrossLanguageLinker()
        hints = linker.detect(parse_results)
        resolved = linker.resolve(hints, func_index)
    """

    def detect(self, parse_results: list[ParseResult]) -> list[ForeignCallHint]:
        """Scan all parse results for cross-language call patterns.

        Args:
            parse_results: Output from all crawlers.

        Returns:
            List of ForeignCallHint objects needing resolution.
        """
        hints: list[ForeignCallHint] = []

        for result in parse_results:
            file_path = str(result.file_info.path)
            language = result.file_info.language

            try:
                source = result.file_info.path.read_text(
                    encoding="utf-8", errors="replace"
                )
            except OSError:
                continue

            if language in ("c", "cpp"):
                hints.extend(self._scan_c_source(source, file_path))
            elif language == "python":
                hints.extend(self._scan_python_source(source, file_path))
            elif language == "shell":
                hints.extend(self._scan_shell_source(source, file_path))

        logger.info("Detected %d cross-language call hints", len(hints))
        return hints

    def _scan_c_source(self, source: str, file_path: str) -> list[ForeignCallHint]:
        """Scan C/C++ source for FFI patterns."""
        hints = []

        for pattern in C_TO_PYTHON:
            for match in pattern.finditer(source):
                line = source[:match.start()].count("\n") + 1
                hints.append(ForeignCallHint(
                    source_file=file_path,
                    source_language="c",
                    caller_name="",  # Resolved later
                    target_name=match.group(1),
                    target_language="python",
                    call_line=line,
                    pattern="c_to_python",
                ))

        for pattern in C_TO_SHELL:
            for match in pattern.finditer(source):
                line = source[:match.start()].count("\n") + 1
                target = match.group(1).split()[0]  # First word of command
                hints.append(ForeignCallHint(
                    source_file=file_path,
                    source_language="c",
                    caller_name="",
                    target_name=target,
                    target_language="shell",
                    call_line=line,
                    pattern="c_to_shell",
                ))

        return hints

    def _scan_python_source(self, source: str, file_path: str) -> list[ForeignCallHint]:
        """Scan Python source for FFI patterns."""
        hints = []

        for pattern in PYTHON_TO_C:
            for match in pattern.finditer(source):
                line = source[:match.start()].count("\n") + 1
                target = match.group(1) if match.lastindex else "unknown"
                hints.append(ForeignCallHint(
                    source_file=file_path,
                    source_language="python",
                    caller_name="",
                    target_name=target,
                    target_language="c",
                    call_line=line,
                    pattern="python_to_c",
                ))

        for pattern in PYTHON_TO_SHELL:
            for match in pattern.finditer(source):
                line = source[:match.start()].count("\n") + 1
                target = match.group(1).split()[0]
                hints.append(ForeignCallHint(
                    source_file=file_path,
                    source_language="python",
                    caller_name="",
                    target_name=target,
                    target_language="shell",
                    call_line=line,
                    pattern="python_to_shell",
                ))

        return hints

    def _scan_shell_source(self, source: str, file_path: str) -> list[ForeignCallHint]:
        """Scan shell source for binary invocations."""
        hints = []

        for pattern in SHELL_TO_BINARY:
            for match in pattern.finditer(source):
                line = source[:match.start()].count("\n") + 1
                target = match.group(1).split("/")[-1]  # Binary name
                hints.append(ForeignCallHint(
                    source_file=file_path,
                    source_language="shell",
                    caller_name="",
                    target_name=target,
                    target_language="c",
                    call_line=line,
                    pattern="shell_to_binary",
                ))

        return hints

    def resolve(
        self,
        hints: list[ForeignCallHint],
        func_name_to_id: dict[str, int],
        db_connection=None,
    ) -> int:
        """Resolve foreign call hints against the function index.

        Inserts resolved edges into the ``calls`` table.

        Returns:
            Number of successfully resolved edges.
        """
        if not db_connection or not hints:
            return 0

        resolved = 0
        for hint in hints:
            callee_id = func_name_to_id.get(hint.target_name)
            if callee_id is None:
                continue

            # Find caller function at the call line
            try:
                caller_row = db_connection.execute(
                    """SELECT f.id FROM Function f
                       JOIN contains_func cf ON f.id = cf.func_id
                       JOIN File fi ON cf.file_id = fi.id
                       WHERE fi.path = ? AND f.start_line <= ? AND f.end_line >= ?
                       LIMIT 1""",
                    [hint.source_file, hint.call_line, hint.call_line],
                ).fetchone()
            except Exception:
                continue

            if not caller_row:
                continue

            try:
                db_connection.execute(
                    "INSERT OR IGNORE INTO calls (caller_id, callee_id, call_site_line) VALUES (?, ?, ?)",
                    [caller_row[0], callee_id, hint.call_line],
                )
                resolved += 1
            except Exception as e:
                logger.debug("Cross-language edge insert failed: %s", e)

        logger.info(
            "Resolved %d / %d cross-language edges",
            resolved, len(hints),
        )
        return resolved
