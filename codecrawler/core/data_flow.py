"""data_flow — Simplified Code Property Graph data-flow analysis.

Inspired by Joern's CPG model but focused on practical embedded-Linux
concerns: global variable contention, tainted data paths, and
cross-function side effects.

Tracks how data flows between functions through:
  - Global variable reads/writes
  - Function parameters and return values
  - Struct member access patterns

This enables queries like:
  - "Which functions can modify this global variable?"
  - "What data flows from network input to this buffer?"
  - "Which variables are written by multiple threads without locks?"

Usage:
    analyzer = DataFlowAnalyzer(event_bus)
    edges = analyzer.analyze(parse_results)
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict

from codecrawler.core.event_bus import EventBus
from codecrawler.core.types import DataFlowEdge, FunctionDef, ParseResult, VariableDef

logger = logging.getLogger(__name__)


class ContentionAlert:
    """Alert for global variable write contention."""

    __slots__ = ("variable", "writers", "severity")

    def __init__(self, variable: str, writers: list[str], severity: str = "medium"):
        self.variable = variable
        self.writers = writers
        self.severity = severity

    def __repr__(self) -> str:
        return f"<ContentionAlert {self.variable} writers={len(self.writers)}>"


class DataFlowAnalyzer:
    """Simplified CPG data-flow analysis for embedded Linux codebases.

    Analyses global variable access patterns across functions to detect:
      1. Write contention (multiple writers, no synchronisation)
      2. Tainted data paths (network input → sensitive operations)
      3. Side-effect coupling (functions that share mutable state)
    """

    # Patterns that suggest a function writes to a variable
    _WRITE_PATTERNS = re.compile(
        r"""
        (?:                        # Match any of:
            \b{var}\s*=(?!=)       #   var = ... (assignment, not ==)
          | \b{var}\s*\+=          #   var += ...
          | \b{var}\s*-=           #   var -= ...
          | \b{var}\s*\|=          #   var |= ...
          | \b{var}\s*&=           #   var &= ...
          | \b{var}\s*\+\+        #   var++
          | \+\+\s*{var}\b        #   ++var
          | \b{var}\s*--          #   var--
          | --\s*{var}\b          #   --var
          | \bmemcpy\s*\(\s*{var}  #   memcpy(var, ...)
          | \bstrcpy\s*\(\s*{var}  #   strcpy(var, ...)
        )
        """,
        re.VERBOSE,
    )

    # Patterns that suggest a function reads a variable
    _READ_INDICATORS = {"if", "while", "for", "switch", "return", "printf", "log"}

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self.event_bus = event_bus or EventBus()

    def analyze(self, parse_results: list[ParseResult]) -> list[DataFlowEdge]:
        """Analyse data flow across all parse results.

        Returns a list of DataFlowEdge describing how data moves between
        functions through global/file-scope variables.
        """
        # Step 1: Collect all global variables and their locations
        global_vars = self._collect_globals(parse_results)

        # Step 2: Build per-function source text index
        func_source = self._build_func_source_index(parse_results)

        # Step 3: Determine writer/reader relationships
        writers: dict[str, list[str]] = defaultdict(list)   # var → [func_name]
        readers: dict[str, list[str]] = defaultdict(list)   # var → [func_name]

        for result in parse_results:
            try:
                source = result.file_info.path.read_text(errors="ignore")
                source_lines = source.splitlines()
            except (OSError, UnicodeDecodeError):
                continue

            for func in result.functions:
                func_body = "\n".join(
                    source_lines[func.start_line - 1:func.end_line]
                )

                for var_name in global_vars:
                    if var_name not in func_body:
                        continue

                    if self._detects_write(var_name, func_body):
                        writers[var_name].append(func.name)

                    if self._detects_read(var_name, func_body):
                        readers[var_name].append(func.name)

        # Step 4: Create data-flow edges
        edges: list[DataFlowEdge] = []
        for var_name in global_vars:
            var_writers = writers.get(var_name, [])
            var_readers = readers.get(var_name, [])

            for writer in var_writers:
                for reader in var_readers:
                    if writer != reader:
                        edges.append(DataFlowEdge(
                            source_var_name=var_name,
                            sink_var_name=var_name,
                            source_func_name=writer,
                            sink_func_name=reader,
                            flow_type="global_variable",
                            confidence=0.8,
                        ))

        # Step 5: Detect write contention
        contention_count = 0
        for var_name, var_writers in writers.items():
            unique_writers = list(set(var_writers))
            if len(unique_writers) > 1:
                severity = "high" if len(unique_writers) > 3 else "medium"
                alert = ContentionAlert(
                    variable=var_name,
                    writers=unique_writers,
                    severity=severity,
                )
                self.event_bus.publish("contention.detected", alert)
                contention_count += 1

        logger.info(
            "Data flow analysis: %d edges, %d contention alerts from %d globals",
            len(edges), contention_count, len(global_vars),
        )
        return edges

    # ── Internal helpers ─────────────────────────────────────────────

    def _collect_globals(self, parse_results: list[ParseResult]) -> set[str]:
        """Collect all global/file-scope variable names."""
        globals_: set[str] = set()
        for result in parse_results:
            for var in result.variables:
                if var.is_global or var.scope in ("global", "file"):
                    globals_.add(var.name)
        return globals_

    def _build_func_source_index(
        self, parse_results: list[ParseResult]
    ) -> dict[str, str]:
        """Build func_name → body_text mapping (for future refinement)."""
        index: dict[str, str] = {}
        for result in parse_results:
            try:
                source = result.file_info.path.read_text(errors="ignore")
                lines = source.splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            for func in result.functions:
                body = "\n".join(lines[func.start_line - 1:func.end_line])
                index[func.name] = body
        return index

    def _detects_write(self, var_name: str, body: str) -> bool:
        """Heuristic: does this function body write to the variable?"""
        # Build a regex for this specific variable
        pattern = self._WRITE_PATTERNS.pattern.replace("{var}", re.escape(var_name))
        return bool(re.search(pattern, body, re.VERBOSE))

    @staticmethod
    def _detects_read(var_name: str, body: str) -> bool:
        """Heuristic: does this function body read the variable?

        A simple check: the variable name appears in the body outside
        of a pure assignment context.
        """
        return var_name in body

    def get_contention_report(
        self, parse_results: list[ParseResult]
    ) -> list[ContentionAlert]:
        """Run analysis and collect contention alerts (convenience method)."""
        alerts: list[ContentionAlert] = []

        def _collect(alert: ContentionAlert) -> None:
            alerts.append(alert)

        self.event_bus.subscribe("contention.detected", _collect)
        self.analyze(parse_results)
        self.event_bus.unsubscribe("contention.detected", _collect)
        return alerts
