"""Python Crawler — AST-based Python source parser."""

from __future__ import annotations

import ast
import logging

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
from codecrawler.plugins.base import PluginBase, PluginManifest

logger = logging.getLogger(__name__)


class PythonCrawler(BaseCrawler):
    """Python source parser using the built-in ast module."""

    @property
    def name(self) -> str:
        return "Python Crawler"

    @property
    def supported_languages(self) -> list[str]:
        return ["python"]

    def parse(self, file_info: FileInfo) -> ParseResult:
        """Parse a Python file using ast."""
        logger.debug("Parsing Python file: %s", file_info.path)

        try:
            source = file_info.path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            logger.error("Could not read %s: %s", file_info.path, e)
            return ParseResult(file_info=file_info)

        try:
            tree = ast.parse(source, filename=str(file_info.path))
        except SyntaxError as e:
            logger.warning("Syntax error in %s: %s", file_info.path, e)
            return ParseResult(file_info=file_info)

        functions: list[FunctionDef] = []
        structs: list[StructDef] = []
        variables: list[VariableDef] = []
        calls: list[CallEdge] = []
        includes: list[IncludeEdge] = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                sig = self._build_signature(node)
                functions.append(FunctionDef(
                    name=node.name,
                    signature=sig,
                    start_line=node.lineno,
                    end_line=node.end_lineno or node.lineno,
                    complexity=self._compute_complexity(node),
                ))

            elif isinstance(node, ast.ClassDef):
                members = []
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        members.append(f"def {item.name}()")
                    elif isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name):
                                members.append(target.id)
                structs.append(StructDef(name=node.name, members=members))

            elif isinstance(node, ast.Call):
                callee = self._get_call_name(node)
                if callee:
                    calls.append(CallEdge(
                        caller="",
                        callee=callee,
                        call_site_line=node.lineno,
                    ))

            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for edge in self._extract_imports(node, str(file_info.path)):
                    includes.append(edge)

            elif isinstance(node, ast.Assign):
                # Module-level variables
                if isinstance(getattr(node, "_parent", None), ast.Module) or True:
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            variables.append(VariableDef(
                                name=target.id,
                                is_global=True,
                                line=node.lineno,
                            ))

        return ParseResult(
            file_info=file_info,
            functions=functions,
            structs=structs,
            variables=variables,
            calls=calls,
            includes=includes,
        )

    def _build_signature(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        """Build a function signature string."""
        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        args = []
        for arg in node.args.args:
            annotation = ""
            if arg.annotation:
                try:
                    annotation = f": {ast.unparse(arg.annotation)}"
                except Exception:
                    pass
            args.append(f"{arg.arg}{annotation}")
        return f"{prefix} {node.name}({', '.join(args)})"

    def _compute_complexity(self, node: ast.AST) -> int:
        """Compute cyclomatic complexity (simplified)."""
        complexity = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
        return complexity

    def _get_call_name(self, node: ast.Call) -> str:
        """Extract the function name from a call node."""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            return node.func.attr
        return ""

    def _extract_imports(self, node: ast.AST, file_path: str) -> list[IncludeEdge]:
        """Extract import edges."""
        edges = []
        if isinstance(node, ast.Import):
            for alias in node.names:
                edges.append(IncludeEdge(source_path=file_path, target_path=alias.name))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            edges.append(IncludeEdge(source_path=file_path, target_path=module))
        return edges


class PythonCrawlerPlugin(PluginBase):
    """Plugin wrapper for the Python crawler."""

    @property
    def manifest(self) -> PluginManifest:
        return PluginManifest(
            name="python_crawler",
            version="4.0.0",
            description="Python AST parser",
            author="Code Crawler Team",
            plugin_type="crawler",
        )

    def register(self, registry) -> None:
        registry.register(BaseCrawler, PythonCrawler())

    def activate(self, event_bus) -> None:
        pass
