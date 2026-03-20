"""Yocto analyzer — parse Bitbake recipes, layers, and DISTRO_FEATURES."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class YoctoLayer:
    """A parsed Yocto/OE layer."""

    name: str
    path: Path
    priority: int = 0
    recipes: list[str] = field(default_factory=list)


@dataclass
class YoctoConfig:
    """Parsed Yocto build configuration."""

    layers: list[YoctoLayer] = field(default_factory=list)
    distro_features: list[str] = field(default_factory=list)
    image_install: list[str] = field(default_factory=list)
    machine: str = ""
    distro: str = ""


def parse_bblayers(bblayers_path: Path) -> list[str]:
    """Parse bblayers.conf to extract layer paths."""
    if not bblayers_path.exists():
        return []

    content = bblayers_path.read_text(encoding="utf-8", errors="replace")
    layers = []

    # Match BBLAYERS assignment
    match = re.search(r'BBLAYERS\s*[?:]?=\s*"([^"]*)"', content, re.DOTALL)
    if match:
        for line in match.group(1).strip().splitlines():
            path = line.strip().rstrip("\\").strip()
            if path and not path.startswith("#"):
                layers.append(path)

    return layers


def parse_local_conf(local_conf_path: Path) -> dict[str, str]:
    """Parse local.conf to extract key configuration variables."""
    if not local_conf_path.exists():
        return {}

    content = local_conf_path.read_text(encoding="utf-8", errors="replace")
    config = {}

    for match in re.finditer(r'^(\w+)\s*[?:]?=\s*"?([^"\n]*)"?', content, re.MULTILINE):
        key, value = match.group(1), match.group(2).strip()
        config[key] = value

    return config


def parse_recipe(recipe_path: Path) -> dict:
    """Parse a Bitbake recipe (.bb) file for key metadata."""
    if not recipe_path.exists():
        return {}

    content = recipe_path.read_text(encoding="utf-8", errors="replace")
    metadata = {"path": str(recipe_path)}

    for key in ("SUMMARY", "DESCRIPTION", "LICENSE", "SRC_URI", "DEPENDS", "RDEPENDS"):
        match = re.search(rf'^{key}\s*[?:]?=\s*"([^"]*)"', content, re.MULTILINE)
        if match:
            metadata[key.lower()] = match.group(1)

    return metadata


def analyze_yocto_project(project_root: Path) -> YoctoConfig:
    """Full Yocto project analysis: layers, config, and features."""
    config = YoctoConfig()

    # Parse bblayers.conf
    bblayers = project_root / "build" / "conf" / "bblayers.conf"
    layer_paths = parse_bblayers(bblayers)

    for layer_path in layer_paths:
        lp = Path(layer_path)
        name = lp.name
        layer = YoctoLayer(name=name, path=lp)

        # Parse layer.conf for priority
        layer_conf = lp / "conf" / "layer.conf"
        if layer_conf.exists():
            lc_content = layer_conf.read_text(encoding="utf-8", errors="replace")
            prio_match = re.search(r"BBFILE_PRIORITY.*=\s*\"?(\d+)\"?", lc_content)
            if prio_match:
                layer.priority = int(prio_match.group(1))

        # Find recipes in this layer
        for recipe in lp.glob("**/*.bb"):
            layer.recipes.append(str(recipe.relative_to(lp)))

        config.layers.append(layer)

    # Parse local.conf
    local_conf = project_root / "build" / "conf" / "local.conf"
    lc_vars = parse_local_conf(local_conf)
    config.machine = lc_vars.get("MACHINE", "")
    config.distro = lc_vars.get("DISTRO", "")

    # Extract DISTRO_FEATURES and IMAGE_INSTALL
    df = lc_vars.get("DISTRO_FEATURES", "")
    config.distro_features = df.split() if df else []

    ii = lc_vars.get("IMAGE_INSTALL", "")
    config.image_install = ii.split() if ii else []

    return config
