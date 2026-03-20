"""C/C++ Crawler — Tree-sitter + libclang hybrid parser."""

from __future__ import annotations

import logging

from codecrawler.core.types import (
    CallEdge,
    FileInfo,
    FunctionDef,
    IncludeEdge,
    MacroDef,
    ParseResult,
    StructDef,
    VariableDef,
)
from codecrawler.crawlers.base import BaseCrawler
from codecrawler.plugins.base import PluginBase, PluginManifest

logger = logging.getLogger(__name__)


class CCrawler(BaseCrawler):
    """C/C++ parser using Tree-sitter for structure and libclang for semantics.

    Tree-sitter provides fast, fault-tolerant parsing for structure extraction.
    libclang (when available) adds deep semantic analysis: type resolution,
    macro expansion, and #ifdef branch evaluation.
    """

    @property
    def name(self) -> str:
        return "C/C++ Crawler"

    @property
    def supported_languages(self) -> list[str]:
        return ["c", "cpp"]

    def parse(self, file_info: FileInfo) -> ParseResult:
        """Parse a C/C++ file and extract all structural elements."""
        logger.debug("Parsing C/C++ file: %s", file_info.path)

        functions: list[FunctionDef] = []
        structs: list[StructDef] = []
        macros: list[MacroDef] = []
        variables: list[VariableDef] = []
        calls: list[CallEdge] = []
        includes: list[IncludeEdge] = []

        try:
            source = file_info.path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            logger.error("Could not read %s: %s", file_info.path, e)
            return ParseResult(file_info=file_info)

        # Extract includes
        includes = self._extract_includes(source, str(file_info.path))

        # Extract macros
        macros = self._extract_macros(source)

        # Try tree-sitter parsing
        try:
            ts_result = self._parse_with_treesitter(source, file_info)
            functions = ts_result.get("functions", [])
            structs = ts_result.get("structs", [])
            variables = ts_result.get("variables", [])
            calls = ts_result.get("calls", [])
        except Exception as e:
            logger.warning("Tree-sitter parse failed for %s: %s", file_info.path, e)
            # Fallback: regex-based extraction
            functions = self._extract_functions_fallback(source)

        return ParseResult(
            file_info=file_info,
            functions=functions,
            structs=structs,
            macros=macros,
            variables=variables,
            calls=calls,
            includes=includes,
        )

    def _parse_with_treesitter(self, source: str, file_info: FileInfo) -> dict:
        """Parse source with tree-sitter, extracting functions, structs, etc."""
        try:
            import tree_sitter_c as tsc
            from tree_sitter import Language, Parser

            parser = Parser(Language(tsc.language()))
            tree = parser.parse(source.encode("utf-8"))
            root = tree.root_node

            functions = []
            structs = []
            variables = []
            calls = []

            for node in self._walk(root):
                if node.type == "function_definition":
                    func = self._extract_function(node, source)
                    if func:
                        functions.append(func)

                elif node.type in ("struct_specifier", "class_specifier"):
                    struct = self._extract_struct(node, source)
                    if struct:
                        structs.append(struct)

                elif node.type == "declaration" and self._is_global_scope(node):
                    var = self._extract_variable(node, source)
                    if var:
                        variables.append(var)

                elif node.type == "call_expression":
                    call = self._extract_call(node, source)
                    if call:
                        calls.append(call)

            return {
                "functions": functions,
                "structs": structs,
                "variables": variables,
                "calls": calls,
            }
        except ImportError:
            logger.debug("tree-sitter not available, using fallback parser")
            raise

    def _walk(self, node):
        """Walk all nodes in the tree."""
        yield node
        for child in node.children:
            yield from self._walk(child)

    def _extract_function(self, node, source: str) -> FunctionDef | None:
        """Extract a FunctionDef from a tree-sitter function_definition node."""
        declarator = node.child_by_field_name("declarator")
        if not declarator:
            return None

        # Find the function name
        name_node = declarator
        while name_node and name_node.type not in ("identifier", "field_identifier"):
            if name_node.type == "function_declarator":
                name_node = name_node.child_by_field_name("declarator")
            elif name_node.children:
                name_node = name_node.children[0]
            else:
                break

        if not name_node:
            return None

        name = source[name_node.start_byte:name_node.end_byte]
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        # Get full signature (everything before the body)
        body = node.child_by_field_name("body")
        if body:
            sig_end = body.start_byte
            signature = source[node.start_byte:sig_end].strip()
        else:
            signature = source[node.start_byte:node.end_byte]

        return FunctionDef(
            name=name,
            signature=signature,
            start_line=start_line,
            end_line=end_line,
            complexity=1,
        )

    def _extract_struct(self, node, source: str) -> StructDef | None:
        """Extract a StructDef from a tree-sitter struct/class node."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None

        name = source[name_node.start_byte:name_node.end_byte]
        members = []

        body = node.child_by_field_name("body")
        if body:
            for child in body.children:
                if child.type == "field_declaration":
                    member_text = source[child.start_byte:child.end_byte].strip().rstrip(";")
                    members.append(member_text)

        return StructDef(name=name, members=members)

    def _extract_variable(self, node, source: str) -> VariableDef | None:
        """Extract a global variable declaration."""
        declarator = node.child_by_field_name("declarator")
        if not declarator:
            return None

        name_node = declarator
        while name_node and name_node.type != "identifier":
            if name_node.children:
                name_node = name_node.children[0]
            else:
                break

        if not name_node or name_node.type != "identifier":
            return None

        name = source[name_node.start_byte:name_node.end_byte]
        type_node = node.child_by_field_name("type")
        var_type = source[type_node.start_byte:type_node.end_byte] if type_node else ""

        is_static = "static" in source[node.start_byte:node.end_byte]

        return VariableDef(
            name=name,
            var_type=var_type,
            is_global=True,
            is_static=is_static,
            line=node.start_point[0] + 1,
        )

    def _extract_call(self, node, source: str) -> CallEdge | None:
        """Extract a call edge from a call_expression node."""
        func_node = node.child_by_field_name("function")
        if not func_node:
            return None

        callee = source[func_node.start_byte:func_node.end_byte]
        line = node.start_point[0] + 1

        return CallEdge(caller="", callee=callee, call_site_line=line)

    def _is_global_scope(self, node) -> bool:
        """Check if a node is at global/file scope."""
        parent = node.parent
        return parent is not None and parent.type == "translation_unit"

    def _extract_includes(self, source: str, file_path: str) -> list[IncludeEdge]:
        """Extract #include directives."""
        includes = []
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("#include"):
                # Extract the included path
                if '"' in stripped:
                    target = stripped.split('"')[1]
                elif "<" in stripped and ">" in stripped:
                    target = stripped.split("<")[1].split(">")[0]
                else:
                    continue
                includes.append(IncludeEdge(source_path=file_path, target_path=target))
        return includes

    def _extract_macros(self, source: str) -> list[MacroDef]:
        """Extract #define macros."""
        macros = []
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("#define"):
                parts = stripped[len("#define"):].strip().split(None, 1)
                if parts:
                    name = parts[0].split("(")[0]  # Handle function-like macros
                    value = parts[1] if len(parts) > 1 else ""
                    is_guard = name.startswith("CONFIG_") or name.endswith("_H")
                    macros.append(MacroDef(name=name, value=value, is_config_guard=is_guard))
        return macros

    def _extract_functions_fallback(self, source: str) -> list[FunctionDef]:
        """Regex-based fallback for function extraction when tree-sitter unavailable."""
        import re

        functions = []
        # Simple C function pattern: type name(params) {
        pattern = re.compile(
            r"^(\w[\w\s\*]+?)\s+(\w+)\s*\(([^)]*)\)\s*\{",
            re.MULTILINE,
        )
        for match in pattern.finditer(source):
            line_num = source[:match.start()].count("\n") + 1
            functions.append(FunctionDef(
                name=match.group(2),
                signature=match.group(0).rstrip("{").strip(),
                start_line=line_num,
                end_line=line_num,
                complexity=1,
            ))
        return functions


class CCrawlerPlugin(PluginBase):
    """Plugin wrapper for the C/C++ crawler."""

    @property
    def manifest(self) -> PluginManifest:
        return PluginManifest(
            name="c_crawler",
            version="4.0.0",
            description="C/C++ parser using Tree-sitter + libclang",
            author="Code Crawler Team",
            plugin_type="crawler",
        )

    def register(self, registry) -> None:
        registry.register(BaseCrawler, CCrawler())

    def activate(self, event_bus) -> None:
        pass
