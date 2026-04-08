//! Code Crawler Native — Rust-accelerated core operations.
//!
//! This crate exposes three hot-path operations to Python via PyO3:
//!   1. `parallel_walk` — multi-threaded directory traversal with SHA-256 hashing
//!   2. `batch_hash`    — parallel file hashing
//!   3. `batch_score`   — vectorized 6-dimension priority scoring

mod hasher;
mod scorer;
mod walker;

use pyo3::prelude::*;

/// The Python module exposed as `codecrawler_native`.
#[pymodule]
fn codecrawler_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(walker::parallel_walk, m)?)?;
    m.add_function(wrap_pyfunction!(hasher::batch_hash, m)?)?;
    m.add_function(wrap_pyfunction!(scorer::batch_score, m)?)?;

    // Expose version info
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
