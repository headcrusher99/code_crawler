"""Telemetry Correlator — map serial logs and crash dumps to AST nodes."""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Common embedded logging macro patterns
LOG_PATTERNS = [
    re.compile(r'(?:printk|pr_err|pr_warn|pr_info|pr_debug)\s*\(\s*"([^"]*)"'),
    re.compile(r'(?:ALOGE|ALOGW|ALOGI|ALOGD|ALOGV)\s*\(\s*"[^"]*"\s*,\s*"([^"]*)"'),
    re.compile(r'(?:RDK_LOG_ERROR|RDK_LOG_WARN|RDK_LOG_INFO|RDK_LOG_DEBUG)\s*\(\s*"[^"]*"\s*,\s*"[^"]*"\s*,\s*"([^"]*)"'),
    re.compile(r'(?:syslog|LOG|log_message)\s*\(\s*\w+\s*,\s*"([^"]*)"'),
    re.compile(r'(?:fprintf)\s*\(\s*stderr\s*,\s*"([^"]*)"'),
]


@dataclass(frozen=True)
class LogLiteral:
    """A log string literal extracted from source code."""

    hash: str
    literal_string: str
    log_level: str
    source_file: str
    line_number: int


@dataclass
class CrashCorrelation:
    """A mapping from a crash log line to AST contexts."""

    log_line: str
    log_hash: str
    matched_functions: list[str] = field(default_factory=list)
    matched_files: list[str] = field(default_factory=list)


class TelemetryCorrelator:
    """Correlates serial log output and crash dumps to source code AST nodes.

    Extracts log string literals from source, hashes them, and enables
    instant lookup when crash logs are ingested.
    """

    def __init__(self, db_connection=None) -> None:
        self.db = db_connection

    def extract_log_literals(self, source: str, file_path: str) -> list[LogLiteral]:
        """Extract all log string literals from a source file.

        Strips format specifiers and hashes the literal for fast lookup.
        """
        literals = []

        for i, line in enumerate(source.splitlines(), 1):
            for pattern in LOG_PATTERNS:
                for match in pattern.finditer(line):
                    raw_string = match.group(1)
                    # Strip format specifiers for stable hashing
                    cleaned = re.sub(r'%[dufslxXp#\-\+0-9.*]*[dufslxXp]', '%s', raw_string)
                    string_hash = hashlib.md5(cleaned.encode()).hexdigest()[:16]

                    # Detect log level from the macro name
                    log_level = self._detect_level(match.group(0))

                    literals.append(LogLiteral(
                        hash=string_hash,
                        literal_string=cleaned,
                        log_level=log_level,
                        source_file=file_path,
                        line_number=i,
                    ))

        return literals

    def correlate_crash_log(self, crash_lines: list[str]) -> list[CrashCorrelation]:
        """Correlate raw crash log lines to AST contexts.

        Hashes each crash log line and looks up matching LogLiteral entries.
        """
        correlations = []

        for line in crash_lines:
            line = line.strip()
            if not line:
                continue

            # Clean and hash the line
            cleaned = re.sub(r'%[dufslxXp#\-\+0-9.*]*[dufslxXp]', '%s', line)
            # Also try stripping timestamps, PIDs, etc.
            cleaned = re.sub(r'^\[[\d\.\s]+\]\s*', '', cleaned)
            cleaned = re.sub(r'^\w{3}\s+\d+\s+[\d:]+\s+\S+\s+', '', cleaned)

            line_hash = hashlib.md5(cleaned.encode()).hexdigest()[:16]

            correlation = CrashCorrelation(log_line=line, log_hash=line_hash)

            # Look up in DB if available
            if self.db:
                try:
                    results = self.db.execute("""
                        SELECT el.func_id, f.name, fi.path
                        FROM LogLiteral ll
                        JOIN emits_log el ON ll.id = el.log_id
                        JOIN Function f ON el.func_id = f.id
                        JOIN contains_func cf ON f.id = cf.func_id
                        JOIN File fi ON cf.file_id = fi.id
                        WHERE ll.hash = ?
                    """, [line_hash]).fetchall()

                    for row in results:
                        correlation.matched_functions.append(row[1])
                        correlation.matched_files.append(row[2])
                except Exception as e:
                    logger.error("Crash correlation query failed: %s", e)

            correlations.append(correlation)

        logger.info(
            "Correlated %d crash lines, %d matched",
            len(crash_lines),
            sum(1 for c in correlations if c.matched_functions),
        )
        return correlations

    def _detect_level(self, macro_call: str) -> str:
        """Detect log level from the macro name."""
        lower = macro_call.lower()
        if "err" in lower or "error" in lower:
            return "error"
        elif "warn" in lower:
            return "warning"
        elif "info" in lower:
            return "info"
        elif "debug" in lower or "dbg" in lower:
            return "debug"
        return "unknown"
