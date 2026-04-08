//! Parallel file walker — uses `ignore` crate for gitignore-aware traversal
//! and `rayon` for multi-threaded directory walking + SHA-256 hashing.

use pyo3::prelude::*;
use pyo3::types::PyDict;
use rayon::prelude::*;
use std::fs;
use std::path::Path;

/// Entry collected from the parallel walk.
struct FileEntry {
    path: String,
    ext: String,
    size: u64,
    hash: String,
}

/// Walk a directory tree in parallel, computing SHA-256 hashes for every file.
///
/// Respects `.gitignore` rules automatically via the `ignore` crate.
/// Returns a list of dicts with keys: path, ext, size, hash.
#[pyfunction]
pub fn parallel_walk(py: Python<'_>, root: &str) -> PyResult<Vec<PyObject>> {
    // Collect all file paths first (single-threaded, but fast)
    let mut paths: Vec<(String, String, u64)> = Vec::new();

    for entry in ignore::WalkBuilder::new(root)
        .hidden(true)        // skip hidden files/dirs
        .git_ignore(true)    // respect .gitignore
        .git_global(true)    // respect global gitignore
        .git_exclude(true)   // respect .git/info/exclude
        .build()
        .filter_map(|e| e.ok())
    {
        let path = entry.path();
        if !path.is_file() {
            continue;
        }

        let ext = path
            .extension()
            .and_then(|e| e.to_str())
            .map(|e| format!(".{}", e.to_lowercase()))
            .unwrap_or_default();

        if ext.is_empty() {
            continue;
        }

        let size = entry.metadata().map(|m| m.len()).unwrap_or(0);
        paths.push((path.to_string_lossy().into_owned(), ext, size));
    }

    // Hash all files in parallel using rayon
    let entries: Vec<FileEntry> = paths
        .into_par_iter()
        .map(|(path, ext, size)| {
            let hash = hash_file(Path::new(&path));
            FileEntry { path, ext, size, hash }
        })
        .collect();

    // Convert to Python dicts
    let results: Vec<PyObject> = entries
        .into_iter()
        .map(|entry| {
            let dict = PyDict::new_bound(py);
            dict.set_item("path", &entry.path).unwrap();
            dict.set_item("ext", &entry.ext).unwrap();
            dict.set_item("size", entry.size).unwrap();
            dict.set_item("hash", &entry.hash).unwrap();
            dict.into()
        })
        .collect();

    Ok(results)
}

/// Compute SHA-256 of a file.
fn hash_file(path: &Path) -> String {
    use sha2::{Digest, Sha256};
    let mut hasher = Sha256::new();
    match fs::read(path) {
        Ok(data) => {
            hasher.update(&data);
            format!("{:x}", hasher.finalize())
        }
        Err(_) => String::new(),
    }
}
