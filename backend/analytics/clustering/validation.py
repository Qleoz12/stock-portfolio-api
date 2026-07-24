"""Cluster validation metrics."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.metrics import (
    calinski_harabasz_score,
    davies_bouldin_score,
    silhouette_samples,
    silhouette_score,
)


@dataclass
class ValidationMetrics:
    average_silhouette: float
    silhouette_per_obs: list[float]
    dunn_index: float
    calinski_harabasz: float
    davies_bouldin: float
    cluster_sizes: dict[int, int]
    negative_silhouette_count: int
    balance_score: float


def dunn_index(X: np.ndarray, labels: np.ndarray) -> float:
    """Dunn index: higher is better (compact + separated clusters)."""
    unique = np.unique(labels)
    if len(unique) < 2:
        return 0.0

    intra_dists = []
    for c in unique:
        mask = labels == c
        pts = X[mask]
        if len(pts) < 2:
            intra_dists.append(0.0)
            continue
        from scipy.spatial.distance import pdist
        intra_dists.append(pdist(pts).max())

    max_intra = max(intra_dists) if intra_dists else 1e-10

    inter_dists = []
    for i, c1 in enumerate(unique):
        for c2 in unique[i + 1:]:
            m1, m2 = labels == c1, labels == c2
            from scipy.spatial.distance import cdist
            d = cdist(X[m1], X[m2]).min()
            inter_dists.append(d)

    min_inter = min(inter_dists) if inter_dists else 0.0
    if max_intra == 0:
        return 0.0
    return float(min_inter / max_intra)


def validate_clusters(X: np.ndarray, labels: np.ndarray) -> ValidationMetrics:
    sil_samples = silhouette_samples(X, labels)
    unique, counts = np.unique(labels, return_counts=True)
    sizes = {int(u): int(c) for u, c in zip(unique, counts)}
    balance = 1.0 - (counts.std() / counts.mean()) if counts.mean() > 0 else 0.0

    return ValidationMetrics(
        average_silhouette=float(silhouette_score(X, labels)),
        silhouette_per_obs=sil_samples.tolist(),
        dunn_index=dunn_index(X, labels),
        calinski_harabasz=float(calinski_harabasz_score(X, labels)),
        davies_bouldin=float(davies_bouldin_score(X, labels)),
        cluster_sizes=sizes,
        negative_silhouette_count=int((sil_samples < 0).sum()),
        balance_score=float(max(0, balance)),
    )


def compare_algorithms(
    results: list,
    X: np.ndarray,
    tickers: list[str],
) -> tuple[str, str]:
    """Pick best algorithm by composite score; return (name, reason)."""
    best_name = ""
    best_score = -1.0
    reasons = []

    for out in results:
        if len(set(out.labels)) < 2:
            continue
        m = validate_clusters(X, out.labels)
        score = (
            m.average_silhouette * 0.35
            + m.dunn_index * 0.25
            + (1.0 / (1.0 + m.davies_bouldin)) * 0.20
            + m.balance_score * 0.20
        )
        name = out.algorithm
        if out.linkage_method:
            name = f"hierarchical_{out.linkage_method}"
        if score > best_score:
            best_score = score
            best_name = name
            reasons = [
                f"silhouette={m.average_silhouette:.3f}",
                f"dunn={m.dunn_index:.3f}",
                f"davies_bouldin={m.davies_bouldin:.3f}",
            ]

    reason = (
        f"Composite score favors {best_name} ({', '.join(reasons)}). "
        "Metrics support the choice but do not replace financial interpretation."
    )
    return best_name, reason
