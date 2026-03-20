"""Manifest Builder — pre-compute IndexManifest bundles for LLM agents."""

from __future__ import annotations

import logging
from dataclasses import asdict

from codecrawler.core.types import FunctionDef, IndexManifestBundle, ParseResult

logger = logging.getLogger(__name__)


class ManifestBuilder:
    """Builds pre-materialized IndexManifest bundles (~500 tokens each).

    IndexManifests compress a file's knowledge from ~15K tokens to ~500 tokens,
    enabling agents to retrieve context in a single MCP call.
    """

    def build(self, parse_result: ParseResult) -> IndexManifestBundle:
        """Build an IndexManifest for a single parsed file.

        The manifest includes:
        - File metadata (path, language, hash, LOC)
        - Function signatures (no bodies)
        - Struct definitions
        - Key macros (#ifdef guards)
        - Call edges (outgoing)
        - Include edges
        """
        file_info = parse_result.file_info

        manifest = {
            "file": {
                "path": str(file_info.path),
                "language": file_info.language,
                "hash": file_info.content_hash,
                "size_bytes": file_info.size_bytes,
                "tier": file_info.tier,
            },
            "functions": [
                {
                    "name": f.name,
                    "signature": f.signature,
                    "lines": f"{f.start_line}-{f.end_line}",
                    "complexity": f.complexity,
                }
                for f in parse_result.functions
            ],
            "structs": [
                {"name": s.name, "members": s.members}
                for s in parse_result.structs
            ],
            "macros": [
                {"name": m.name, "is_guard": m.is_config_guard}
                for m in parse_result.macros
                if m.is_config_guard  # Only include config guards in manifest
            ],
            "calls_out": [
                {"callee": c.callee, "line": c.call_site_line}
                for c in parse_result.calls
            ],
            "includes": [
                {"target": i.target_path}
                for i in parse_result.includes
            ],
            "globals": [
                {"name": v.name, "type": v.var_type}
                for v in parse_result.variables
                if v.is_global
            ],
        }

        return IndexManifestBundle(
            file_path=str(file_info.path),
            manifest_json=manifest,
        )

    def build_batch(self, results: list[ParseResult]) -> list[IndexManifestBundle]:
        """Build IndexManifests for a batch of parsed files."""
        manifests = []
        for result in results:
            try:
                manifest = self.build(result)
                manifests.append(manifest)
            except Exception:
                logger.exception("Failed to build manifest for %s", result.file_info.path)
        logger.info("Built %d IndexManifests", len(manifests))
        return manifests
