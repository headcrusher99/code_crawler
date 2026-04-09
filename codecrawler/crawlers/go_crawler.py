"""go_crawler — Go source file parser.

Extracts functions, structs, interfaces, and call edges from Go source
using regex patterns (no external Go parser dependency required).
"""

from __future__ import annotations

import logging
import re

from codecrawler.core.types import (
    CallEdge,
    FileInfo,
    FunctionDef,
    IncludeEdge,
    ParseResult,
    StructDef,
    VariableDef,
)
from codecrawler.crawlers.base import BaseCrawler

logger = logging.getLogger(__name__)


class GoCrawler(BaseCrawler):
    """Parser for Go (.go) source files.

    Extracts:
      - Functions and methods (with receiver)
      - Struct and interface definitions
      - Import statements
      - Global var/const declarations
      - Function call edges
    """

    @property
    def name(self) -> str:
        return "Go Crawler"

    @property
    def supported_languages(self) -> list[str]:
        return ["go"]

    # ── Regex patterns ───────────────────────────────────────────────

    _FUNC_PATTERN = re.compile(
        r"""
        func\s+                              # func keyword
        (?:\((?P<recv>\w+\s+\*?\w+)\)\s+)?   # Optional receiver
        (?P<name>\w+)                        # Function name
        \s*\((?P<params>[^)]*)\)             # Parameters
        (?:\s*\((?P<ret_multi>[^)]*)\)       # Multiple return values
         |\s*(?P<ret_single>[\w\*\[\]]+))?   # Single return value
        \s*\{                                # Opening brace
        """,
        re.VERBOSE,
    )

    _STRUCT_PATTERN = re.compile(
        r"type\s+(?P<name>\w+)\s+(?P<kind>struct|interface)\s*\{"
    )

    _IMPORT_SINGLE = re.compile(r'import\s+"([^"]+)"')
    _IMPORT_BLOCK = re.compile(r"import\s*\((.*?)\)", re.DOTALL)
    _IMPORT_ITEM = re.compile(r'"([^"]+)"')

    _VAR_PATTERN = re.compile(
        r"var\s+(?P<name>\w+)\s+(?P<type>[\w\*\[\]\.]+)"
    )

    _CALL_PATTERN = re.compile(r"\b(?P<name>\w+)\s*\(")

    def parse(self, file_info: FileInfo) -> ParseResult:
        """Parse a Go source file."""
        try:
            source = file_info.path.read_text(errors="ignore")
        except OSError:
            return ParseResult(file_info=file_info)

        lines = source.splitlines()

        functions = self._extract_functions(source, lines)
        structs = self._extract_structs(source, lines)
        includes = self._extract_imports(source, str(file_info.path))
        variables = self._extract_globals(source)
        calls = self._extract_calls(source, lines, functions)

        return ParseResult(
            file_info=file_info,
            functions=functions,
            structs=structs,
            variables=variables,
            calls=calls,
            includes=includes,
        )

    def _extract_functions(
        self, source: str, lines: list[str]
    ) -> list[FunctionDef]:
        """Extract Go function and method definitions."""
        functions: list[FunctionDef] = []

        for match in self._FUNC_PATTERN.finditer(source):
            name = match.group("name")
            recv = match.group("recv") or ""
            params = match.group("params").strip()
            ret = match.group("ret_multi") or match.group("ret_single") or ""

            start_pos = match.start()
            start_line = source[:start_pos].count("\n") + 1
            end_line = self._find_closing_brace(lines, start_line - 1)

            # Build signature
            sig = "func "
            if recv:
                sig += f"({recv}) "
            sig += f"{name}({params})"
            if ret:
                ret = ret.strip()
                sig += f" {ret}"

            # Complexity estimate
            body = "\n".join(lines[start_line - 1:end_line])
            complexity = self._estimate_complexity(body)

            # Exported = starts with uppercase in Go
            is_exported = name[0].isupper() if name else False

            functions.append(FunctionDef(
                name=name,
                signature=sig,
                start_line=start_line,
                end_line=end_line,
                complexity=complexity,
                return_type=ret.strip(),
                is_static=not is_exported,
                is_exported=is_exported,
                language="go",
            ))

        return functions

    def _extract_structs(
        self, source: str, lines: list[str]
    ) -> list[StructDef]:
        """Extract struct and interface definitions."""
        structs: list[StructDef] = []

        for match in self._STRUCT_PATTERN.finditer(source):
            name = match.group("name")
            kind = match.group("kind")
            start_pos = match.start()
            start_line = source[:start_pos].count("\n") + 1
            end_line = self._find_closing_brace(lines, start_line - 1)

            body = "\n".join(lines[start_line:end_line - 1])
            members = self._extract_members(body, kind)

            structs.append(StructDef(
                name=name,
                members=members,
                kind=kind,
                start_line=start_line,
                end_line=end_line,
            ))

        return structs

    def _extract_imports(
        self, source: str, file_path: str
    ) -> list[IncludeEdge]:
        """Extract import statements."""
        includes: list[IncludeEdge] = []

        # Single imports
        for match in self._IMPORT_SINGLE.finditer(source):
            includes.append(IncludeEdge(
                source_path=file_path,
                target_path=match.group(1),
            ))

        # Block imports
        for block in self._IMPORT_BLOCK.finditer(source):
            for item in self._IMPORT_ITEM.finditer(block.group(1)):
                includes.append(IncludeEdge(
                    source_path=file_path,
                    target_path=item.group(1),
                ))

        return includes

    def _extract_globals(self, source: str) -> list[VariableDef]:
        """Extract package-level variable declarations."""
        variables: list[VariableDef] = []

        for match in self._VAR_PATTERN.finditer(source):
            # Only capture top-level vars (not indented)
            pos = match.start()
            line_start = source.rfind("\n", 0, pos) + 1
            indent = pos - line_start
            if indent == 0:
                variables.append(VariableDef(
                    name=match.group("name"),
                    var_type=match.group("type"),
                    is_global=True,
                    scope="global",
                ))

        return variables

    def _extract_calls(
        self,
        source: str,
        lines: list[str],
        functions: list[FunctionDef],
    ) -> list[CallEdge]:
        """Extract function call edges within function bodies."""
        calls: list[CallEdge] = []
        skip = {
            "func", "if", "for", "switch", "select", "case", "go",
            "defer", "return", "range", "make", "new", "append", "len",
            "cap", "close", "copy", "delete", "panic", "recover",
            "print", "println", "complex", "imag", "real", "type",
            "var", "const", "map", "chan", "nil", "true", "false",
            "string", "int", "float64", "bool", "byte", "error",
        }

        for func in functions:
            body = "\n".join(lines[func.start_line - 1:func.end_line])
            for match in self._CALL_PATTERN.finditer(body):
                callee = match.group("name")
                if callee not in skip and callee != func.name:
                    call_line = func.start_line + body[:match.start()].count("\n")
                    calls.append(CallEdge(
                        caller=func.name,
                        callee=callee,
                        call_site_line=call_line,
                    ))

        return calls

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _find_closing_brace(lines: list[str], start_idx: int) -> int:
        depth = 0
        for i in range(start_idx, len(lines)):
            depth += lines[i].count("{") - lines[i].count("}")
            if depth <= 0 and i > start_idx:
                return i + 1
        return min(start_idx + 1, len(lines))

    @staticmethod
    def _estimate_complexity(body: str) -> int:
        keywords = ["if ", "else", "for ", "switch", "select", "case ", "&&", "||"]
        return 1 + sum(body.count(kw) for kw in keywords)

    @staticmethod
    def _extract_members(body: str, kind: str) -> list[str]:
        members: list[str] = []
        for line in body.splitlines():
            line = line.strip()
            if not line or line.startswith("//") or line.startswith("/*"):
                continue
            parts = line.split()
            if parts and parts[0].isidentifier():
                if kind == "interface":
                    # Method signature
                    members.append(parts[0])
                else:
                    # Struct field
                    members.append(parts[0])
        return members
