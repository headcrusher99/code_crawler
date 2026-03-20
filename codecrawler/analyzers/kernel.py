"""Kernel analyzer — parse Kconfig, .config, and generate compile_commands.json."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class KernelConfig:
    """Parsed Linux kernel configuration."""

    enabled_configs: dict[str, str] = field(default_factory=dict)  # CONFIG_FOO=y/m/value
    disabled_configs: list[str] = field(default_factory=list)
    arch: str = ""
    version: str = ""


def parse_kernel_dotconfig(config_path: Path) -> KernelConfig:
    """Parse a Linux kernel .config file.

    Extracts enabled/disabled CONFIG_ symbols.
    """
    result = KernelConfig()

    if not config_path.exists():
        logger.warning("Kernel .config not found at %s", config_path)
        return result

    content = config_path.read_text(encoding="utf-8", errors="replace")

    for line in content.splitlines():
        line = line.strip()

        if line.startswith("#") and "is not set" in line:
            match = re.match(r"#\s*(CONFIG_\w+)\s+is not set", line)
            if match:
                result.disabled_configs.append(match.group(1))

        elif line.startswith("CONFIG_") and "=" in line:
            key, _, value = line.partition("=")
            result.enabled_configs[key] = value.strip('"')

    # Try to detect arch
    arch = result.enabled_configs.get("CONFIG_ARCH", "")
    if not arch:
        for key in result.enabled_configs:
            if key.startswith("CONFIG_ARCH_"):
                arch = key.replace("CONFIG_ARCH_", "").lower()
                break
    result.arch = arch

    logger.info(
        "Kernel config: %d enabled, %d disabled symbols (arch=%s)",
        len(result.enabled_configs),
        len(result.disabled_configs),
        result.arch,
    )
    return result


def build_ifdef_symbol_table(config: KernelConfig) -> dict[str, bool]:
    """Build a symbol table for #ifdef resolution.

    Maps CONFIG_FOO → True/False for use during C parsing
    to determine which #ifdef branches are active.
    """
    symbols = {}

    for key, value in config.enabled_configs.items():
        symbols[key] = True
        # Also add without CONFIG_ prefix
        if key.startswith("CONFIG_"):
            symbols[key[7:]] = True

    for key in config.disabled_configs:
        symbols[key] = False
        if key.startswith("CONFIG_"):
            symbols[key[7:]] = False

    return symbols


def generate_compile_commands(
    kernel_root: Path,
    output_path: Path | None = None,
) -> Path | None:
    """Generate compile_commands.json for the kernel tree.

    This enables libclang to resolve includes, macros, and types properly.
    """
    if output_path is None:
        output_path = kernel_root / "compile_commands.json"

    # Check if kernel already has compile_commands.json
    existing = kernel_root / "compile_commands.json"
    if existing.exists():
        logger.info("Using existing compile_commands.json at %s", existing)
        return existing

    # Try to generate via kernel's built-in script
    gen_script = kernel_root / "scripts" / "clang-tools" / "gen_compile_commands.py"
    if gen_script.exists():
        logger.info("Kernel has gen_compile_commands.py — run it manually for best results")
        return None

    # Fallback: generate a minimal compile_commands.json from source files
    logger.info("Generating minimal compile_commands.json")
    entries = []
    for c_file in kernel_root.rglob("*.c"):
        if any(part.startswith(".") for part in c_file.parts):
            continue
        entries.append({
            "directory": str(kernel_root),
            "command": f"cc -c {c_file.relative_to(kernel_root)} -I{kernel_root}/include",
            "file": str(c_file.relative_to(kernel_root)),
        })
        if len(entries) >= 10000:  # Cap for sanity
            break

    output_path.write_text(json.dumps(entries, indent=2))
    logger.info("Generated compile_commands.json with %d entries", len(entries))
    return output_path
