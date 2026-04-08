//! Batch file hasher — parallel SHA-256 computation across multiple files.

use pyo3::prelude::*;
use rayon::prelude::*;
use sha2::{Digest, Sha256};
use std::fs;
use std::path::Path;

/// Hash multiple files in parallel, returning their SHA-256 hex digests.
///
/// # Arguments
/// * `paths` — list of file path strings
///
/// # Returns
/// List of hex-encoded SHA-256 hashes (empty string on read failure).
#[pyfunction]
pub fn batch_hash(paths: Vec<String>) -> Vec<String> {
    paths
        .into_par_iter()
        .map(|path| {
            let p = Path::new(&path);
            match fs::read(p) {
                Ok(data) => {
                    let mut hasher = Sha256::new();
                    hasher.update(&data);
                    format!("{:x}", hasher.finalize())
                }
                Err(_) => String::new(),
            }
        })
        .collect()
}
