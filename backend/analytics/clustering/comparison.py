"""Transparent algorithm comparison and ranking."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from analytics.clustering.validation import validate_clusters

METRIC_WEIGHTS = {
    "average_silhouette": 0.30,
    "dunn_index": 0.20,
    "calinski_harabasz": 0.15,
    "davies_bouldin": 0.15,
    "balance_score": 0.10,
    "negative_silhouette_penalty": 0.10,
}


@dataclass
class AlgorithmScoreRow:
    algorithm: str
    linkage: str | None
    raw_metrics: dict[str, float]
    normalized_scores: dict[str, float]
    weights: dict[str, float]
    contributions: dict[str, float]
    composite_score: float
    rank: int = 0
    status: str = "candidate"  # clear_winner, exploratory_best, no_clear_winner


def _normalize_higher(values: list[float]) -> list[float]:
    if not values:
        return []
    mn, mx = min(values), max(values)
    if mx == mn:
        return [0.5] * len(values)
    return [(v - mn) / (mx - mn) for v in values]


def _normalize_lower(values: list[float]) -> list[float]:
    if not values:
        return []
    mn, mx = min(values), max(values)
    if mx == mn:
        return [0.5] * len(values)
    return [(mx - v) / (mx - mn) for v in values]


def compare_algorithms_transparent(
    results: list,
    X: np.ndarray,
    tickers: list[str],
    weak_structure: bool = False,
) -> tuple[list[AlgorithmScoreRow], str, str]:
    """Return full ranking table, winner name, status."""
    seen: set[str] = set()
    rows: list[AlgorithmScoreRow] = []

    for out in results:
        name = out.algorithm
        if out.linkage_method:
            name = f"hierarchical_{out.linkage_method}"
        if name in seen:
            continue
        seen.add(name)

        if len(set(out.labels)) < 2:
            continue

        m = validate_clusters(X, out.labels)
        raw = {
            "average_silhouette": m.average_silhouette,
            "dunn_index": m.dunn_index,
            "calinski_harabasz": m.calinski_harabasz,
            "davies_bouldin": m.davies_bouldin,
            "balance_score": m.balance_score,
            "negative_silhouette_count": float(m.negative_silhouette_count),
        }
        rows.append(AlgorithmScoreRow(
            algorithm=name,
            linkage=out.linkage_method,
            raw_metrics=raw,
            normalized_scores={},
            weights=dict(METRIC_WEIGHTS),
            contributions={},
            composite_score=0.0,
        ))

    if not rows:
        return [], "", "no_clear_winner"

    # Normalize across algorithms
    sil_vals = [r.raw_metrics["average_silhouette"] for r in rows]
    dunn_vals = [r.raw_metrics["dunn_index"] for r in rows]
    ch_vals = [r.raw_metrics["calinski_harabasz"] for r in rows]
    db_vals = [r.raw_metrics["davies_bouldin"] for r in rows]
    bal_vals = [r.raw_metrics["balance_score"] for r in rows]
    neg_vals = [r.raw_metrics["negative_silhouette_count"] for r in rows]

    sil_n = _normalize_higher(sil_vals)
    dunn_n = _normalize_higher(dunn_vals)
    ch_n = _normalize_higher(ch_vals)
    db_n = _normalize_lower(db_vals)
    bal_n = _normalize_higher(bal_vals)
    neg_n = _normalize_lower(neg_vals)

    for i, row in enumerate(rows):
        row.normalized_scores = {
            "average_silhouette": sil_n[i],
            "dunn_index": dunn_n[i],
            "calinski_harabasz": ch_n[i],
            "davies_bouldin": db_n[i],
            "balance_score": bal_n[i],
            "negative_silhouette_penalty": neg_n[i],
        }
        contrib = {}
        total = 0.0
        for metric, weight in METRIC_WEIGHTS.items():
            key = metric if metric in row.normalized_scores else "negative_silhouette_penalty"
            if metric == "negative_silhouette_penalty":
                key = "negative_silhouette_penalty"
            val = row.normalized_scores.get(key, 0)
            c = val * weight
            contrib[metric] = round(c, 4)
            total += c
        row.contributions = contrib
        row.composite_score = round(total, 4)

    rows.sort(key=lambda r: r.composite_score, reverse=True)
    for i, row in enumerate(rows):
        row.rank = i + 1

    best = rows[0]
    second = rows[1] if len(rows) > 1 else None
    margin = best.composite_score - (second.composite_score if second else 0)

    if weak_structure:
        status = "exploratory_best"
        winner_status = "Exploratory best candidate"
    elif margin < 0.05:
        status = "no_clear_winner"
        winner_status = "No clear winner"
    else:
        status = "clear_winner"
        winner_status = "Clear winner"

    best.status = status
    reason = (
        f"{winner_status}: {best.algorithm} (composite={best.composite_score:.3f}, "
        f"silhouette={best.raw_metrics['average_silhouette']:.3f}, "
        f"dunn={best.raw_metrics['dunn_index']:.3f}). "
        "Metrics support the choice but do not replace financial interpretation."
    )
    return rows, best.algorithm, reason
