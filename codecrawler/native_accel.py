"""Native Acceleration Shim — Python fallback for Rust-accelerated operations.

This module tries to import the ``codecrawler_native`` Rust extension.
If it's not installed, every function degrades to a pure-Python fallback
transparently.

Accelerated operations:
    • fast_discover_files  — parallel directory walk + SHA-256 hashing
    • fast_hash_files      — batch parallel file hashing
    • fast_batch_score     — vectorized 6-dimension priority scoring
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Attempt to load the Rust extension
_NATIVE_AVAILABLE = False
_native = None

try:
    import codecrawler_native as _native  # type: ignore[import-not-found]

    _NATIVE_AVAILABLE = True
    logger.info("Rust native acceleration loaded (codecrawler_native)")
except ImportError:
    logger.debug("codecrawler_native not found — using pure-Python fallback")


def is_available() -> bool:
    """Check if native acceleration is available."""
    return _NATIVE_AVAILABLE


# ── Parallel File Discovery ──────────────────────────────────────────

def fast_discover_files(root: str) -> list[dict]:
    """Discover files with parallel walking and hashing.

    Returns list of dicts with keys: path, ext, size, hash.

    Uses Rust ``parallel_walk`` if available, otherwise falls back
    to Python ``os.walk`` + ``hashlib``.
    """
    if _NATIVE_AVAILABLE and _native is not None:
        try:
            return _native.parallel_walk(root)
        except Exception as e:
            logger.warning("Native walker failed, falling back: %s", e)

    return _py_discover_files(root)


def _py_discover_files(root: str) -> list[dict]:
    """Pure-Python file discovery (fallback)."""
    results = []
    root_path = Path(root).resolve()

    for dirpath, _dirnames, filenames in os.walk(root_path):
        dir_path = Path(dirpath)
        if any(part.startswith(".") for part in dir_path.parts):
            continue

        for filename in filenames:
            file_path = dir_path / filename
            ext = file_path.suffix.lower()
            if not ext:
                continue

            try:
                stat = file_path.stat()
                file_hash = _hash_file(file_path)
            except OSError:
                continue

            results.append({
                "path": str(file_path),
                "ext": ext,
                "size": stat.st_size,
                "hash": file_hash,
            })

    return results


# ── Batch File Hashing ──────────────────────────────────────────────

def fast_hash_files(paths: list[str]) -> list[str]:
    """Hash multiple files in parallel.

    Returns list of SHA-256 hex digests, one per input path.
    """
    if _NATIVE_AVAILABLE and _native is not None:
        try:
            return _native.batch_hash(paths)
        except Exception as e:
            logger.warning("Native hasher failed, falling back: %s", e)

    return [_hash_file(Path(p)) for p in paths]


# ── Batch Priority Scoring ──────────────────────────────────────────

def fast_batch_score(
    func_ids: list[int],
    tier_levels: list[float],
    usage_freqs: list[float],
    centralities: list[float],
    build_actives: list[float],
    runtime_freqs: list[float],
    recencies: list[float],
    weights: dict[str, float],
) -> list[float]:
    """Compute composite priority scores for a batch of functions.

    Returns list of composite scores.
    """
    if _NATIVE_AVAILABLE and _native is not None:
        try:
            return _native.batch_score(
                func_ids, tier_levels, usage_freqs, centralities,
                build_actives, runtime_freqs, recencies,
                weights.get("tier", 0.25),
                weights.get("usage", 0.20),
                weights.get("centrality", 0.15),
                weights.get("build", 0.10),
                weights.get("runtime", 0.15),
                weights.get("recency", 0.15),
            )
        except Exception as e:
            logger.warning("Native scorer failed, falling back: %s", e)

    # Pure-Python fallback
    w = weights
    results = []
    for i in range(len(func_ids)):
        score = (
            tier_levels[i] * w.get("tier", 0.25)
            + usage_freqs[i] * w.get("usage", 0.20)
            + centralities[i] * w.get("centrality", 0.15)
            + build_actives[i] * w.get("build", 0.10)
            + runtime_freqs[i] * w.get("runtime", 0.15)
            + recencies[i] * w.get("recency", 0.15)
        )
        results.append(round(score, 6))
    return results


# ── Internal helpers ────────────────────────────────────────────────

def _hash_file(path: Path, block_size: int = 65536) -> str:
    """Compute SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(block_size), b""):
                hasher.update(block)
    except OSError:
        return ""
    return hasher.hexdigest()
