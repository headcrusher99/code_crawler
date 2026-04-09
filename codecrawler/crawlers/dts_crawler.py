"""dts_crawler — Device Tree Source (.dts/.dtsi) parser.

Extracts device tree nodes, compatible strings, status, and properties
from Device Tree Source files used in embedded Linux boards.

This enables:
  - Mapping device tree nodes → kernel drivers via compatible strings
  - Understanding hardware configuration for a specific board
  - Detecting enabled/disabled peripherals
"""

from __future__ import annotations

import logging
import re

from codecrawler.core.types import (
    FileInfo,
    FunctionDef,
    MacroDef,
    ParseResult,
    StructDef,
    VariableDef,
)
from codecrawler.crawlers.base import BaseCrawler

logger = logging.getLogger(__name__)


class DTSCrawler(BaseCrawler):
    """Parser for Device Tree Source (.dts/.dtsi) files.

    Extracts device tree nodes as StructDef entries (since DTS nodes
    are essentially struct-like data descriptions) and compatible
    strings as MacroDef entries for cross-referencing with drivers.
    """

    @property
    def name(self) -> str:
        return "Device Tree Source Crawler"

    @property
    def supported_languages(self) -> list[str]:
        return ["devicetree"]

    # Regex patterns for DTS parsing
    _NODE_PATTERN = re.compile(
        r"""
        (?P<name>\S+?)          # Node name
        (?:@(?P<addr>[0-9a-fA-F]+))?  # Optional unit address
        \s*\{                   # Opening brace
        """,
        re.VERBOSE,
    )

    _COMPATIBLE_PATTERN = re.compile(
        r'compatible\s*=\s*"([^"]+)"(?:\s*,\s*"([^"]+)")*\s*;'
    )

    _STATUS_PATTERN = re.compile(r'status\s*=\s*"(\w+)"\s*;')

    _PROPERTY_PATTERN = re.compile(
        r"(\w[\w-]*)\s*=\s*(.+?)\s*;", re.DOTALL
    )

    _INCLUDE_PATTERN = re.compile(
        r"""
        (?:
            /include/\s+"([^"]+)"     # DTS /include/ directive
          | \#include\s+[<"]([^>"]+)[>"]  # C-style #include
        )
        """,
        re.VERBOSE,
    )

    def parse(self, file_info: FileInfo) -> ParseResult:
        """Parse a DTS/DTSI file into structural elements."""
        try:
            source = file_info.path.read_text(errors="ignore")
        except OSError:
            return ParseResult(file_info=file_info)

        structs: list[StructDef] = []
        macros: list[MacroDef] = []
        variables: list[VariableDef] = []
        includes = []

        # Extract includes
        for match in self._INCLUDE_PATTERN.finditer(source):
            inc_path = match.group(1) or match.group(2)
            if inc_path:
                from codecrawler.core.types import IncludeEdge
                includes.append(IncludeEdge(
                    source_path=str(file_info.path),
                    target_path=inc_path,
                ))

        # Parse nodes (simplified — tracks top-level and first-level nodes)
        nodes = self._extract_nodes(source)
        for node in nodes:
            # Represent DT nodes as StructDef with members as properties
            members = list(node.get("properties", {}).keys())
            structs.append(StructDef(
                name=node["name"],
                members=members,
                kind="device_tree_node",
                start_line=node.get("line", 0),
                summary=f"DT node: {node.get('path', node['name'])}",
            ))

            # Compatible strings → MacroDef for driver matching
            for compat in node.get("compatible", []):
                macros.append(MacroDef(
                    name=f"dt_compatible:{compat}",
                    value=compat,
                    is_config_guard=False,
                    line=node.get("line", 0),
                ))

            # Status → VariableDef for enabled/disabled tracking
            status = node.get("status", "okay")
            variables.append(VariableDef(
                name=f"dt_status:{node['name']}",
                var_type="string",
                is_global=True,
                scope="global",
                line=node.get("line", 0),
            ))

        return ParseResult(
            file_info=file_info,
            structs=structs,
            macros=macros,
            variables=variables,
            includes=includes,
        )

    def _extract_nodes(self, source: str) -> list[dict]:
        """Extract device tree nodes from DTS source.

        Returns a list of node dictionaries with name, path, compatible
        strings, status, and properties.
        """
        nodes: list[dict] = []
        lines = source.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Skip comments
            if line.startswith("//") or line.startswith("/*"):
                i += 1
                continue

            # Look for node definitions
            match = self._NODE_PATTERN.match(line)
            if match:
                node_name = match.group("name")
                addr = match.group("addr")
                full_name = f"{node_name}@{addr}" if addr else node_name

                # Skip root node marker and labels
                if node_name in ("/", "&"):
                    i += 1
                    continue

                # Collect node body
                brace_depth = 1
                node_start = i
                body_lines: list[str] = []
                i += 1
                while i < len(lines) and brace_depth > 0:
                    body_line = lines[i]
                    brace_depth += body_line.count("{") - body_line.count("}")
                    body_lines.append(body_line)
                    i += 1

                body = "\n".join(body_lines)

                # Extract properties
                properties: dict[str, str] = {}
                for prop_match in self._PROPERTY_PATTERN.finditer(body):
                    properties[prop_match.group(1)] = prop_match.group(2).strip()

                # Extract compatible strings
                compatibles: list[str] = []
                for compat_match in re.finditer(r'"([^"]+)"', properties.get("compatible", "")):
                    compatibles.append(compat_match.group(1))

                # Extract status
                status_match = self._STATUS_PATTERN.search(body)
                status = status_match.group(1) if status_match else "okay"

                nodes.append({
                    "name": full_name,
                    "path": f"/{full_name}",
                    "compatible": compatibles,
                    "status": status,
                    "properties": properties,
                    "line": node_start + 1,
                })
            else:
                i += 1

        return nodes
