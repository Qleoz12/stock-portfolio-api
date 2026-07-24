"""Clustering tendency: Hopkins statistic and VAT."""
from __future__ import annotations

import numpy as np
from sklearn.neighbors import NearestNeighbors


def hopkins_statistic(X: np.ndarray, sample_size: int | None = None, random_state: int = 42) -> float:
    """
    Hopkins statistic: ~0.5 = random, >0.7 = clusterable, ~1.0 = strong structure.
    """
    rng = np.random.default_rng(random_state)
    n, d = X.shape
    if n < 10:
        return 0.5

    m = sample_size or min(int(n * 0.1), 50)
    m = max(5, min(m, n - 1))

    mins = X.min(axis=0)
    maxs = X.max(axis=0)
    span = maxs - mins
    span[span == 0] = 1.0

    # Random points in feature space
    u = rng.random((m, d)) * span + mins

    # Real points sample
    idx = rng.choice(n, size=m, replace=False)
    X_sample = X[idx]

    nn = NearestNeighbors(n_neighbors=2).fit(X)
    u_dist, _ = nn.kneighbors(u)
    w = u_dist[:, 0].sum()

    x_dist, _ = nn.kneighbors(X_sample)
    v = x_dist[:, 1].sum()

    if w + v == 0:
        return 0.5
    return float(v / (w + v))


def vat_ordering(dist_matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Visual Assessment of Tendency: reorder distance matrix for heatmap.
    Returns (reordered_matrix, ordering_indices).
    """
    n = dist_matrix.shape[0]
    if n == 0:
        return dist_matrix, np.array([])

    D = dist_matrix.copy()
    ordering = [0]
    remaining = set(range(1, n))

    while remaining:
        last = ordering[-1]
        min_dist = float("inf")
        next_idx = None
        for j in remaining:
            d = D[last, j]
            if d < min_dist:
                min_dist = d
                next_idx = j
        ordering.append(next_idx)
        remaining.remove(next_idx)

    order = np.array(ordering)
    return D[np.ix_(order, order)], order


def interpret_hopkins(h: float) -> str:
    if h >= 0.75:
        return "Strong clustering tendency detected."
    if h >= 0.55:
        return "Moderate clustering tendency."
    if h >= 0.45:
        return "Weak or no clear clustering structure (near random)."
    return "Data appears similar to uniform random distribution."


def hopkins_status(h: float) -> dict:
    """
    Hopkins convention (sklearn-style): values near 1 = clusterable, near 0.5 = random.
    Library: custom implementation using sklearn.neighbors.NearestNeighbors.
    """
    if h >= 0.75:
        level, state = "strong", "PASS"
        meaning = "Meaningful clustering tendency is supported."
    elif h >= 0.65:
        level, state = "moderate", "PASS"
        meaning = "Moderate clustering tendency."
    elif h >= 0.55:
        level, state = "weak", "EXPLORATORY"
        meaning = "Weak clustering tendency. Analysis may continue with warnings."
    elif h >= 0.45:
        level, state = "random", "EXPLORATORY"
        meaning = "Approximately random. Exploratory analysis only."
    else:
        level, state = "none", "FAIL"
        meaning = "No convincing compact cluster structure was found."

    return {
        "value": h,
        "level": level,
        "state": state,
        "meaning": meaning,
        "library": "sklearn.neighbors.NearestNeighbors (custom Hopkins implementation)",
        "convention": "Values near 1.0 = clusterable; near 0.5 = random",
        "actions": [
            "Reduce features", "Select another profile", "Change universe",
            "Change time window", "Use PCA", "Continue exploratory analysis",
        ] if state != "PASS" else [],
    }
