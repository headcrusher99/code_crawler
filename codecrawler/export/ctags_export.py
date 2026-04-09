"""ctags_export — Export index as Universal Ctags format.

Generates a tags file compatible with vim, emacs, and any editor
that supports the ctags format (Universal Ctags v2).

Usage:
    exporter = CtagsExporter(db_connection)
    exporter.export(Path("tags"))
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class CtagsExporter:
    """Export the Code Crawler index as a Universal Ctags-compatible tags file.

    The output follows ctags file format 2 with extensions:
      - language: field
      - signature: for functions
      - access:private for static functions
      - kind: f (function), s (struct), m (macro), v (variable)

    This allows developers to use vim/emacs tag navigation on the
    Code Crawler index without needing to run ctags separately.
    """

    def __init__(self, db_connection=None) -> None:
        self.db = db_connection

    def export(self, output: Path, project_root: Path | None = None) -> int:
        """Export all indexed entities to a ctags file.

        Args:
            output: Path to write the tags file.
            project_root: If set, paths are made relative to this root.

        Returns:
            Number of tags written.
        """
        if self.db is None:
            logger.warning("No database connection — cannot export ctags")
            return 0

        tags: list[str] = []

        # Functions
        tags.extend(self._export_functions(project_root))

        # Structs
        tags.extend(self._export_structs(project_root))

        # Macros
        tags.extend(self._export_macros(project_root))

        # Variables (global only)
        tags.extend(self._export_variables(project_root))

        # Sort tags (ctags format requires sorted output)
        tags.sort()

        # Write file with header
        with open(output, "w") as fh:
            fh.write("!_TAG_FILE_FORMAT\t2\t/extended format/\n")
            fh.write("!_TAG_FILE_SORTED\t1\t/0=unsorted, 1=sorted/\n")
            fh.write("!_TAG_PROGRAM_NAME\tcodecrawler\t//\n")
            fh.write("!_TAG_PROGRAM_VERSION\t5.0\t//\n")
            fh.write("!_TAG_PROGRAM_URL\thttps://github.com/headcrusher99/code_crawler\t//\n")
            for tag in tags:
                fh.write(tag + "\n")

        logger.info("Exported %d tags to %s", len(tags), output)
        return len(tags)

    def export_from_results(
        self,
        parse_results: list,
        output: Path,
        project_root: Path | None = None,
    ) -> int:
        """Export directly from ParseResult objects (no DB needed).

        Useful for quick tag generation during development.
        """
        tags: list[str] = []

        for result in parse_results:
            file_path = self._relative_path(str(result.file_info.path), project_root)

            for func in result.functions:
                extras = [f"language:{result.file_info.language}"]
                if func.signature:
                    extras.append(f"signature:{func.signature}")
                if func.is_static:
                    extras.append("access:private")
                extra_str = "\t".join(extras)
                tags.append(
                    f"{func.name}\t{file_path}\t{func.start_line};\"\tf\t{extra_str}"
                )

            for struct in result.structs:
                kind = "s" if struct.kind in ("struct", "class") else "g"
                tags.append(
                    f"{struct.name}\t{file_path}\t{struct.start_line};\"\t{kind}\t"
                    f"language:{result.file_info.language}"
                )

            for macro in result.macros:
                tags.append(
                    f"{macro.name}\t{file_path}\t{macro.line};\"\td\t"
                    f"language:{result.file_info.language}"
                )

        tags.sort()

        with open(output, "w") as fh:
            fh.write("!_TAG_FILE_FORMAT\t2\t/extended format/\n")
            fh.write("!_TAG_FILE_SORTED\t1\t/0=unsorted, 1=sorted/\n")
            fh.write("!_TAG_PROGRAM_NAME\tcodecrawler\t//\n")
            fh.write("!_TAG_PROGRAM_VERSION\t5.0\t//\n")
            for tag in tags:
                fh.write(tag + "\n")

        logger.info("Exported %d tags to %s (from results)", len(tags), output)
        return len(tags)

    # ── Per-entity exporters ─────────────────────────────────────────

    def _export_functions(self, project_root: Path | None) -> list[str]:
        """Export all functions as ctags entries."""
        tags: list[str] = []
        try:
            rows = self.db.execute("""
                SELECT f.name, fi.path, f.start_line, fi.language,
                       f.signature
                FROM Function f
                JOIN File fi ON f.file_id = fi.id
                ORDER BY fi.path, f.start_line
            """).fetchall()
        except Exception:
            return tags

        for name, path, line, lang, sig in rows:
            path = self._relative_path(path, project_root)
            extras = [f"language:{lang}"]
            if sig:
                extras.append(f"signature:{sig}")
            extra_str = "\t".join(extras)
            tags.append(f"{name}\t{path}\t{line};\"\tf\t{extra_str}")

        return tags

    def _export_structs(self, project_root: Path | None) -> list[str]:
        """Export all structs as ctags entries."""
        tags: list[str] = []
        try:
            rows = self.db.execute("""
                SELECT s.name, fi.path, fi.language
                FROM Struct s
                JOIN File fi ON s.file_id = fi.id
            """).fetchall()
        except Exception:
            return tags

        for name, path, lang in rows:
            path = self._relative_path(path, project_root)
            tags.append(f"{name}\t{path}\t1;\"\ts\tlanguage:{lang}")

        return tags

    def _export_macros(self, project_root: Path | None) -> list[str]:
        """Export all macros as ctags entries."""
        tags: list[str] = []
        try:
            rows = self.db.execute("""
                SELECT m.name, fi.path, fi.language
                FROM Macro m
                JOIN File fi ON m.file_id = fi.id
            """).fetchall()
        except Exception:
            return tags

        for name, path, lang in rows:
            path = self._relative_path(path, project_root)
            tags.append(f"{name}\t{path}\t1;\"\td\tlanguage:{lang}")

        return tags

    def _export_variables(self, project_root: Path | None) -> list[str]:
        """Export global variables as ctags entries."""
        tags: list[str] = []
        try:
            rows = self.db.execute("""
                SELECT v.name, fi.path, fi.language
                FROM Variable v
                JOIN File fi ON v.file_id = fi.id
                WHERE v.is_global = TRUE
            """).fetchall()
        except Exception:
            return tags

        for name, path, lang in rows:
            path = self._relative_path(path, project_root)
            tags.append(f"{name}\t{path}\t1;\"\tv\tlanguage:{lang}")

        return tags

    @staticmethod
    def _relative_path(path: str, root: Path | None) -> str:
        """Make a path relative to project root if given."""
        if root is None:
            return path
        try:
            return str(Path(path).relative_to(root))
        except ValueError:
            return path
