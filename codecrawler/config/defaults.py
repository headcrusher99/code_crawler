"""Default configuration template and schema."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_TOML = '''# ══════════════════════════════════════════════
# Code Crawler Configuration (.codecrawler.toml)
# ══════════════════════════════════════════════

[project]
name = "my-project"
type = "generic"                    # yocto | buildroot | kernel | android | openwrt | generic
root = "."

[index]
# Glob patterns for tier assignment
# full = fully indexed (i3), skeleton = signatures only (i2), stub = path+hash (i1)
# Everything not matched defaults to i0 (ignored)
tiers = { full = ["src/**", "app/**"], skeleton = ["lib/**"], stub = ["**"] }

[build]
config_file = ""                    # Path to build .config
layers_file = ""                    # Path to bblayers.conf (Yocto)
kernel_config = ""                  # Path to kernel .config
compile_commands = "auto"           # "auto" | path to compile_commands.json

[llm]
provider = "ollama"                 # ollama | openai | anthropic
model = "llama3.2:8b"

[embeddings]
model = "sentence-transformers/all-MiniLM-L6-v2"
device = "cpu"                      # cpu | cuda | mps

[tiering]
llm_proposer_model = "llama3.2:3b"
git_evidence_months = 6             # Look back N months for git activity

[priority_scoring]
weights = { tier = 0.25, usage = 0.20, centrality = 0.15, build = 0.10, runtime = 0.15, recency = 0.15 }
self_tuning = true

[collaboration]
enabled = false
master_db_path = "shared/codecrawler_master.db"
swarm_compute = false
developer_id = "dev-default"

[git]
semantic_patch_enabled = true
branch_isolation = true

[telemetry]
enabled = false
sources = ["gdb_traces", "valgrind", "asan_logs", "serial_uart_logs"]
auto_patch_generation = false

[plugins]
search_paths = ["./plugins"]
enabled = ["*"]                     # List of plugin names, or ["*"] for all
disabled = []

[storage]
db_path = ".codecrawler/index.duckdb"
'''


def write_default_config(output_path: str = ".codecrawler.toml") -> Path:
    """Write the default configuration file.

    Args:
        output_path: Path to write the config file.

    Returns:
        Path to the written config file.
    """
    path = Path(output_path)

    if path.exists():
        logger.warning("Config file already exists at %s, not overwriting", path)
        return path

    path.write_text(DEFAULT_CONFIG_TOML)
    logger.info("Default config written to %s", path)
    return path
