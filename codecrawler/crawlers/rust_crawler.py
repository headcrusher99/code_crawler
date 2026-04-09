"""rust_crawler — Rust source file parser.

Uses tree-sitter-rust (when available) or regex fallback to extract
functions, structs, enums, traits, and call edges from Rust source.
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


class RustCrawler(BaseCrawler):
    """Parser for Rust (.rs) source files.

    Extracts:
      - Functions (fn), methods (impl blocks)
      - Structs, enums, and trait definitions
      - Use statements (imports)
      - Function calls
      - Static/const variables
    """

    @property
    def name(self) -> str:
        return "Rust Crawler"

    @property
    def supported_languages(self) -> list[str]:
        return ["rust"]

    # ── Regex patterns ───────────────────────────────────────────────

    _FN_PATTERN = re.compile(
        r"""
        (?:pub\s+(?:\(crate\)\s+)?)?   # Optional pub visibility
        (?:async\s+)?                   # Optional async
        (?:unsafe\s+)?                  # Optional unsafe
        fn\s+                           # fn keyword
        (?P<name>\w+)                   # Function name
        (?:<[^>]*>)?                    # Optional generics
        \s*\((?P<params>[^)]*)\)        # Parameters
        (?:\s*->\s*(?P<ret>[^{]+?))?    # Optional return type
        \s*(?:where[^{]*)?\{           # Opening brace
        """,
        re.VERBOSE,
    )

    _STRUCT_PATTERN = re.compile(
        r"""
        (?:pub\s+)?                     # Optional pub
        (?:struct|enum|union|trait)      # Type keyword
        \s+(?P<name>\w+)               # Name
        (?:<[^>]*>)?                    # Optional generics
        """,
        re.VERBOSE,
    )

    _USE_PATTERN = re.compile(r"use\s+([\w:]+(?:::\{[^}]+\})?)\s*;")

    _CALL_PATTERN = re.compile(r"\b(\w+)\s*(?:::\w+)*\s*\(")

    _STATIC_PATTERN = re.compile(
        r"(?:pub\s+)?static\s+(?:mut\s+)?(\w+)\s*:\s*([^=;]+)"
    )

    _CONST_PATTERN = re.compile(
        r"(?:pub\s+)?const\s+(\w+)\s*:\s*([^=;]+)"
    )

    def parse(self, file_info: FileInfo) -> ParseResult:
        """Parse a Rust source file."""
        try:
            source = file_info.path.read_text(errors="ignore")
        except OSError:
            return ParseResult(file_info=file_info)

        lines = source.splitlines()

        functions = self._extract_functions(source, lines)
        structs = self._extract_structs(source, lines)
        includes = self._extract_uses(source, str(file_info.path))
        variables = self._extract_statics(source)
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
        """Extract function definitions."""
        functions: list[FunctionDef] = []

        for match in self._FN_PATTERN.finditer(source):
            name = match.group("name")
            params = match.group("params").strip()
            ret = (match.group("ret") or "").strip()
            start_pos = match.start()
            start_line = source[:start_pos].count("\n") + 1

            # Find the end of the function body
            end_line = self._find_closing_brace(lines, start_line - 1)

            # Build signature
            sig_parts = [f"fn {name}({params})"]
            if ret:
                sig_parts.append(f"-> {ret}")
            signature = " ".join(sig_parts)

            # Calculate cyclomatic complexity (simplified)
            body = "\n".join(lines[start_line - 1:end_line])
            complexity = self._estimate_complexity(body)

            # Check if pub
            line_text = lines[start_line - 1] if start_line <= len(lines) else ""
            is_exported = "pub" in line_text

            functions.append(FunctionDef(
                name=name,
                signature=signature,
                start_line=start_line,
                end_line=end_line,
                complexity=complexity,
                return_type=ret,
                is_static=not is_exported,
                is_exported=is_exported,
                language="rust",
            ))

        return functions

    def _extract_structs(
        self, source: str, lines: list[str]
    ) -> list[StructDef]:
        """Extract struct, enum, union, and trait definitions."""
        structs: list[StructDef] = []

        for match in self._STRUCT_PATTERN.finditer(source):
            name = match.group("name")
            start_pos = match.start()
            start_line = source[:start_pos].count("\n") + 1

            # Determine kind
            text = source[match.start():match.end()]
            if "struct" in text:
                kind = "struct"
            elif "enum" in text:
                kind = "enum"
            elif "union" in text:
                kind = "union"
            elif "trait" in text:
                kind = "trait"
            else:
                kind = "struct"

            # Extract members (simplified)
            end_line = self._find_closing_brace(lines, start_line - 1)
            body = "\n".join(lines[start_line:end_line])
            members = self._extract_struct_members(body)

            structs.append(StructDef(
                name=name,
                members=members,
                kind=kind,
                start_line=start_line,
                end_line=end_line,
            ))

        return structs

    def _extract_uses(
        self, source: str, file_path: str
    ) -> list[IncludeEdge]:
        """Extract use statements as include edges."""
        includes: list[IncludeEdge] = []
        for match in self._USE_PATTERN.finditer(source):
            path = match.group(1)
            includes.append(IncludeEdge(
                source_path=file_path,
                target_path=path,
            ))
        return includes

    def _extract_statics(self, source: str) -> list[VariableDef]:
        """Extract static and const variable declarations."""
        variables: list[VariableDef] = []

        for match in self._STATIC_PATTERN.finditer(source):
            name = match.group(1)
            var_type = match.group(2).strip()
            is_mut = "mut" in source[match.start():match.end()]
            variables.append(VariableDef(
                name=name,
                var_type=var_type,
                is_global=True,
                is_static=True,
                is_volatile=is_mut,
                scope="global",
            ))

        for match in self._CONST_PATTERN.finditer(source):
            name = match.group(1)
            var_type = match.group(2).strip()
            variables.append(VariableDef(
                name=name,
                var_type=var_type,
                is_global=True,
                is_const=True,
                scope="global",
            ))

        return variables

    def _extract_calls(
        self,
        source: str,
        lines: list[str],
        functions: list[FunctionDef],
    ) -> list[CallEdge]:
        """Extract function call edges (within function bodies)."""
        calls: list[CallEdge] = []
        known_funcs = {f.name for f in functions}

        # Rust keywords and built-ins to skip
        skip = {
            "fn", "if", "while", "for", "loop", "match", "let", "mut",
            "return", "break", "continue", "pub", "use", "mod", "struct",
            "enum", "trait", "impl", "where", "as", "in", "ref", "self",
            "Self", "super", "crate", "type", "const", "static", "unsafe",
            "async", "await", "move", "dyn", "Box", "Vec", "String",
            "Option", "Result", "Some", "None", "Ok", "Err", "println",
            "eprintln", "format", "print", "eprint", "write", "writeln",
        }

        for func in functions:
            body = "\n".join(lines[func.start_line - 1:func.end_line])
            for match in self._CALL_PATTERN.finditer(body):
                callee = match.group(1)
                if callee not in skip and callee != func.name:
                    call_line = (
                        func.start_line
                        + body[:match.start()].count("\n")
                    )
                    calls.append(CallEdge(
                        caller=func.name,
                        callee=callee,
                        call_site_line=call_line,
                    ))

        return calls

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _find_closing_brace(lines: list[str], start_idx: int) -> int:
        """Find the line with the matching closing brace."""
        depth = 0
        for i in range(start_idx, len(lines)):
            depth += lines[i].count("{") - lines[i].count("}")
            if depth <= 0 and i > start_idx:
                return i + 1
        return min(start_idx + 1, len(lines))

    @staticmethod
    def _estimate_complexity(body: str) -> int:
        """Estimate cyclomatic complexity from branch keywords."""
        keywords = ["if ", "else", "match", "while", "for ", "loop", "?", "&&", "||"]
        return 1 + sum(body.count(kw) for kw in keywords)

    @staticmethod
    def _extract_struct_members(body: str) -> list[str]:
        """Extract member names from a struct/enum body."""
        members: list[str] = []
        for line in body.splitlines():
            line = line.strip().rstrip(",")
            if ":" in line and not line.startswith("//"):
                member_name = line.split(":")[0].strip()
                if member_name and member_name.isidentifier():
                    members.append(member_name)
            elif line and line[0].isalpha() and not line.startswith("//"):
                # Enum variant
                variant = line.split("(")[0].split("{")[0].strip()
                if variant and variant.isidentifier():
                    members.append(variant)
        return members
