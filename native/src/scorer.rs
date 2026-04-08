//! Batch priority scorer — vectorized 6-dimension composite scoring.
//!
//! Computes: composite = Σ (dimension_i × weight_i) for all functions in one call.

use pyo3::prelude::*;

/// Compute composite priority scores for a batch of functions.
///
/// Each input vector must have the same length (one element per function).
/// Weights are the 6 coefficients: w_tier, w_usage, w_centrality, w_build, w_runtime, w_recency.
///
/// Returns a vector of composite scores, one per function.
#[pyfunction]
#[pyo3(signature = (
    _func_ids,
    tier_levels,
    usage_freqs,
    centralities,
    build_actives,
    runtime_freqs,
    recencies,
    w_tier,
    w_usage,
    w_centrality,
    w_build,
    w_runtime,
    w_recency
))]
pub fn batch_score(
    _func_ids: Vec<i64>,
    tier_levels: Vec<f64>,
    usage_freqs: Vec<f64>,
    centralities: Vec<f64>,
    build_actives: Vec<f64>,
    runtime_freqs: Vec<f64>,
    recencies: Vec<f64>,
    w_tier: f64,
    w_usage: f64,
    w_centrality: f64,
    w_build: f64,
    w_runtime: f64,
    w_recency: f64,
) -> Vec<f64> {
    let n = tier_levels.len();
    let mut scores = Vec::with_capacity(n);

    for i in 0..n {
        let s = tier_levels[i] * w_tier
            + usage_freqs[i] * w_usage
            + centralities[i] * w_centrality
            + build_actives[i] * w_build
            + runtime_freqs[i] * w_runtime
            + recencies[i] * w_recency;

        // Round to 6 decimal places
        scores.push((s * 1_000_000.0).round() / 1_000_000.0);
    }

    scores
}
