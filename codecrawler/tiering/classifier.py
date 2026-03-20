"""Tier Classifier — LLM-based directory tier classification (i0–i3)."""

from __future__ import annotations

import logging
from pathlib import Path

from codecrawler.core.config import TieringConfig
from codecrawler.core.types import FileInfo, TierClassification

logger = logging.getLogger(__name__)

# Well-known directories that can be classified without an LLM
KNOWN_I0_DIRS = {
    "binutils", "gcc", "glibc", "uclibc", "musl", "toolchain",
    "busybox", "coreutils", "util-linux", "ncurses", "zlib",
    ".git", "__pycache__", "node_modules", ".venv",
}

KNOWN_I1_DIRS = {
    "systemd", "dbus", "avahi", "udev", "pam", "openssl",
    "libnl", "iptables", "iproute2", "hostapd", "wpa_supplicant",
}

KNOWN_I3_KEYWORDS = {
    "custom", "vendor", "proprietary", "app", "application",
    "service", "daemon", "agent", "manager", "hal",
}


class TierClassifier:
    """Classifies directories and files into tiers (i0–i3).

    Uses a 3-phase pipeline:
    1. Pre-trained knowledge classification (LLM or heuristics)
    2. Git evidence validation (recent commits bump the tier)
    3. Build-config cross-reference (active targets bump the tier)
    """

    def __init__(self, config: TieringConfig | None = None) -> None:
        self.config = config or TieringConfig()

    def classify(self, files: list[FileInfo]) -> list[TierClassification]:
        """Classify a batch of files into tiers.

        Groups by top-level directory first, then classifies each directory.
        """
        # Group files by their top-level directory
        dir_files: dict[str, list[FileInfo]] = {}
        for f in files:
            parts = f.path.parts
            # Use the first meaningful directory component
            top_dir = parts[0] if len(parts) > 0 else "."
            dir_files.setdefault(top_dir, []).append(f)

        classifications = []
        for dir_name, dir_file_list in dir_files.items():
            tier = self._classify_directory(dir_name)
            for f in dir_file_list:
                classifications.append(TierClassification(
                    path=str(f.path),
                    tier=tier,
                    confidence=0.8 if tier in (0, 3) else 0.6,
                    source="heuristic",
                ))

        logger.info("Classified %d files into tiers", len(classifications))
        return classifications

    def _classify_directory(self, dir_name: str) -> int:
        """Classify a directory using heuristic rules.

        In v5, this will be replaced/augmented with actual LLM calls.
        """
        lower = dir_name.lower()

        # Phase 1: Known directory classification
        if lower in KNOWN_I0_DIRS:
            return 0

        if lower in KNOWN_I1_DIRS:
            return 1

        for keyword in KNOWN_I3_KEYWORDS:
            if keyword in lower:
                return 3

        # Default to i2 (skeleton) for unknown directories
        return 2

    def classify_with_llm(self, directory_tree: str) -> list[TierClassification]:
        """Classify using an LLM (placeholder for v5 implementation).

        Will use a sub-7B model like Llama-3.2-3B to leverage pre-trained
        knowledge about open-source code directories.
        """
        logger.info("LLM classification is planned for v5")
        return []
