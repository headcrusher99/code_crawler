"""Buildroot analyzer — parse .config and package selections."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class BuildrootConfig:
    """Parsed Buildroot configuration."""

    enabled_packages: list[str] = field(default_factory=list)
    disabled_packages: list[str] = field(default_factory=list)
    target_arch: str = ""
    toolchain: str = ""
    custom_configs: dict[str, str] = field(default_factory=dict)


def parse_dotconfig(config_path: Path) -> BuildrootConfig:
    """Parse a Buildroot .config file.

    Extracts enabled/disabled packages, target architecture,
    and custom configurations.
    """
    result = BuildrootConfig()

    if not config_path.exists():
        logger.warning("Buildroot .config not found at %s", config_path)
        return result

    content = config_path.read_text(encoding="utf-8", errors="replace")

    for line in content.splitlines():
        line = line.strip()

        if line.startswith("#") and "is not set" in line:
            # Disabled config: # BR2_PACKAGE_FOO is not set
            match = re.match(r"#\s*(BR2_PACKAGE_\w+)\s+is not set", line)
            if match:
                pkg_name = match.group(1).replace("BR2_PACKAGE_", "").lower()
                result.disabled_packages.append(pkg_name)

        elif line.startswith("BR2_PACKAGE_") and "=y" in line:
            # Enabled package
            key = line.split("=")[0]
            pkg_name = key.replace("BR2_PACKAGE_", "").lower()
            result.enabled_packages.append(pkg_name)

        elif line.startswith("BR2_ARCH="):
            result.target_arch = line.split("=", 1)[1].strip('"')

        elif line.startswith("BR2_TOOLCHAIN"):
            key, _, value = line.partition("=")
            result.custom_configs[key] = value.strip('"')

    logger.info(
        "Buildroot config: %d enabled, %d disabled packages",
        len(result.enabled_packages),
        len(result.disabled_packages),
    )
    return result


def get_package_source_dirs(project_root: Path, package_name: str) -> list[Path]:
    """Get source directories for a Buildroot package."""
    candidates = [
        project_root / "package" / package_name,
        project_root / "output" / "build" / f"{package_name}-*",
    ]

    results = []
    for candidate in candidates:
        if "*" in str(candidate):
            results.extend(candidate.parent.glob(candidate.name))
        elif candidate.is_dir():
            results.append(candidate)
    return results
