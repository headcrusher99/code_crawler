"""compile_db — Unified compile_commands.json handler.

Inspired by Google Kythe's extractor model and Ericsson CodeCompass.
Provides precise #ifdef resolution, include-path resolution, and
dead-code identification for C/C++ embedded Linux builds.

Usage:
    handler = CompilationDatabaseHandler.from_file("compile_commands.json")
    ctx = handler.get_context("src/wifi_hal.c")
    active_defines = ctx.defines
    include_paths = ctx.include_paths
    is_compiled = handler.is_file_compiled("src/wifi_hal.c")
"""

from __future__ import annotations

import json
import logging
import shlex
import subprocess
from pathlib import Path

from codecrawler.core.types import CompileContext, CompileEntry

logger = logging.getLogger(__name__)


class CompilationDatabaseHandler:
    """Parse and utilise compile_commands.json for precise C/C++ analysis.

    compile_commands.json provides:
      - Exact compiler flags (-D defines, -I include paths)
      - Which files are actually compiled (vs dead code)
      - Optimisation level, target architecture

    This eliminates the #ifdef guessing problem that plagues every other
    code indexer when dealing with embedded Linux builds.
    """

    def __init__(self, entries: list[CompileEntry]) -> None:
        self._entries = entries
        self._by_file: dict[str, CompileEntry] = {}
        for entry in entries:
            # Normalise to absolute path
            fpath = entry.file
            if not Path(fpath).is_absolute() and entry.directory:
                fpath = str(Path(entry.directory) / fpath)
            self._by_file[self._normalise(fpath)] = entry
        logger.info(
            "Loaded compilation database with %d entries", len(self._entries)
        )

    # ── Factory methods ──────────────────────────────────────────────

    @classmethod
    def from_file(cls, path: str | Path) -> CompilationDatabaseHandler:
        """Load from a compile_commands.json file."""
        path = Path(path)
        if not path.exists():
            logger.warning("compile_commands.json not found at %s", path)
            return cls([])
        with open(path) as fh:
            raw = json.load(fh)
        entries = [
            CompileEntry(
                file=e.get("file", ""),
                directory=e.get("directory", ""),
                command=e.get("command", ""),
                arguments=e.get("arguments", []),
            )
            for e in raw
        ]
        return cls(entries)

    @classmethod
    def empty(cls) -> CompilationDatabaseHandler:
        """Return a no-op handler when no compile_commands.json exists."""
        return cls([])

    # ── Public API ───────────────────────────────────────────────────

    def get_context(self, file_path: str) -> CompileContext:
        """Get full compilation context for a file."""
        entry = self._find_entry(file_path)
        if entry is None:
            return CompileContext(file_path=file_path)

        args = entry.arguments or shlex.split(entry.command or "")
        defines = self._extract_defines(args)
        includes = self._extract_includes(args, entry.directory)
        compiler = args[0] if args else "gcc"
        standard = self._extract_flag(args, "-std=")
        optimization = self._extract_flag(args, "-O")

        return CompileContext(
            defines=frozenset(defines),
            include_paths=tuple(includes),
            compiler=compiler,
            standard=standard,
            optimization=f"-O{optimization}" if optimization else "",
            file_path=file_path,
        )

    def get_defines(self, file_path: str) -> set[str]:
        """Get all -D defines active for a specific file."""
        ctx = self.get_context(file_path)
        return set(ctx.defines)

    def get_include_paths(self, file_path: str) -> list[str]:
        """Get all -I include paths active for a specific file."""
        ctx = self.get_context(file_path)
        return list(ctx.include_paths)

    def is_file_compiled(self, file_path: str) -> bool:
        """Check if a file appears in compile_commands.json."""
        return self._find_entry(file_path) is not None

    def get_active_ifdef_branches(self, file_path: str) -> dict[str, bool]:
        """Determine which #ifdef macros are defined for this file."""
        defines = self.get_defines(file_path)
        return {d.split("=")[0]: True for d in defines}

    @property
    def compiled_files(self) -> list[str]:
        """List all files that are in the compilation database."""
        return list(self._by_file.keys())

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    # ── Generators ───────────────────────────────────────────────────

    @staticmethod
    def generate_for_kernel(kernel_root: Path) -> Path | None:
        """Generate compile_commands.json for a Linux kernel tree."""
        target = kernel_root / "compile_commands.json"
        if target.exists():
            return target
        try:
            subprocess.run(
                ["make", "compile_commands.json"],
                cwd=str(kernel_root),
                capture_output=True,
                timeout=120,
            )
            if target.exists():
                logger.info("Generated compile_commands.json for kernel")
                return target
        except Exception:
            logger.debug("Could not generate kernel compile_commands.json")
        return None

    @staticmethod
    def generate_with_bear(build_dir: Path, build_cmd: str = "make") -> Path | None:
        """Use Bear to intercept build commands and generate compile_commands.json."""
        target = build_dir / "compile_commands.json"
        try:
            subprocess.run(
                ["bear", "--", build_cmd],
                cwd=str(build_dir),
                capture_output=True,
                timeout=600,
            )
            if target.exists():
                logger.info("Generated compile_commands.json with Bear")
                return target
        except FileNotFoundError:
            logger.debug("Bear not installed, cannot generate compile_commands.json")
        except Exception:
            logger.debug("Bear generation failed")
        return None

    # ── Internals ────────────────────────────────────────────────────

    def _find_entry(self, file_path: str) -> CompileEntry | None:
        """Find the compilation entry for a file (with path normalisation)."""
        normalised = self._normalise(file_path)
        entry = self._by_file.get(normalised)
        if entry:
            return entry
        # Fallback: match by basename
        basename = Path(file_path).name
        for key, ent in self._by_file.items():
            if Path(key).name == basename:
                return ent
        return None

    @staticmethod
    def _normalise(path: str) -> str:
        """Normalise a path for consistent lookup."""
        try:
            return str(Path(path).resolve())
        except (OSError, ValueError):
            return path

    @staticmethod
    def _extract_defines(args: list[str]) -> list[str]:
        """Extract -D define flags from compiler arguments."""
        defines: list[str] = []
        i = 0
        while i < len(args):
            arg = args[i]
            if arg == "-D" and i + 1 < len(args):
                defines.append(args[i + 1])
                i += 2
            elif arg.startswith("-D"):
                defines.append(arg[2:])
                i += 1
            else:
                i += 1
        return defines

    @staticmethod
    def _extract_includes(args: list[str], base_dir: str = "") -> list[str]:
        """Extract -I include path flags from compiler arguments."""
        paths: list[str] = []
        i = 0
        while i < len(args):
            arg = args[i]
            raw_path = ""
            if arg == "-I" and i + 1 < len(args):
                raw_path = args[i + 1]
                i += 2
            elif arg.startswith("-I"):
                raw_path = arg[2:]
                i += 1
            else:
                i += 1
                continue

            # Resolve relative paths
            if raw_path and not Path(raw_path).is_absolute() and base_dir:
                raw_path = str(Path(base_dir) / raw_path)
            if raw_path:
                paths.append(raw_path)
        return paths

    @staticmethod
    def _extract_flag(args: list[str], prefix: str) -> str:
        """Extract a flag value from compiler arguments (e.g., -std=c11 → c11)."""
        for arg in args:
            if arg.startswith(prefix):
                return arg[len(prefix):]
        return ""

    def __repr__(self) -> str:
        return f"<CompilationDatabaseHandler entries={len(self._entries)}>"
