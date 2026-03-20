"""Build System Detector — auto-detect Yocto, Buildroot, Kernel, or generic."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Build system detection signatures
BUILD_SIGNATURES: dict[str, list[str]] = {
    "yocto": [
        "meta-*/conf/layer.conf",
        "poky/",
        "build/conf/bblayers.conf",
        "build/conf/local.conf",
        "*.bb",
    ],
    "buildroot": [
        "Config.in",
        "package/*/Config.in",
        "configs/*_defconfig",
        "Makefile.legacy",
        "support/",
    ],
    "kernel": [
        "Kconfig",
        "Kbuild",
        "arch/",
        "drivers/",
        "include/linux/",
        "kernel/",
    ],
    "android": [
        "Android.bp",
        "Android.mk",
        "build/envsetup.sh",
        "device/",
        "hardware/",
    ],
    "openwrt": [
        "feeds.conf.default",
        "target/linux/",
        "package/network/",
        "include/target.mk",
    ],
}


def detect_build_system(project_root: Path) -> str | None:
    """Auto-detect the build system based on filesystem signatures.

    Args:
        project_root: Path to the project root directory.

    Returns:
        Build system type string, or None if no specific system detected.
    """
    project_root = project_root.resolve()

    if not project_root.is_dir():
        logger.warning("Project root %s is not a directory", project_root)
        return None

    scores: dict[str, int] = {}

    for build_type, signatures in BUILD_SIGNATURES.items():
        score = 0
        for sig in signatures:
            # Check for glob patterns
            if "*" in sig:
                matches = list(project_root.glob(sig))
                if matches:
                    score += len(matches)
            else:
                if (project_root / sig).exists():
                    score += 2  # Exact match is worth more
        scores[build_type] = score

    if not scores or max(scores.values()) == 0:
        logger.info("No specific build system detected in %s", project_root)
        return None

    detected = max(scores, key=scores.get)
    confidence = scores[detected]
    logger.info("Detected build system: %s (score=%d)", detected, confidence)
    return detected
