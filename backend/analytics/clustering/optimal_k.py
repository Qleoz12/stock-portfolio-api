"""Optimal number of clusters."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import calinski_harabasz_score, davies_bouldin_score, silhouette_score


@dataclass
class OptimalKResult:
    k_range: list[int]
    elbow_inertia: dict[int, float]
    silhouette_scores: dict[int, float]
    gap_scores: dict[int, float]
    calinski_scores: dict[int, float]
    davies_bouldin_scores: dict[int, float]
    recommendations: dict[str, int]
    consensus_k: int
    agreement_level: str
    agreement_label: str = "Low"
    alternatives: list[int] | None = None


def _gap_statistic(X: np.ndarray, k: int, n_refs: int = 10, random_state: int = 42) -> float:
    rng = np.random.default_rng(random_state)
    mins = X.min(axis=0)
    maxs = X.max(axis=0)
    refs = [rng.uniform(mins, maxs, size=X.shape) for _ in range(n_refs)]

    km = KMeans(n_clusters=k, random_state=random_state, n_init=10)
    km.fit(X)
    Wk = km.inertia_

    ref_Wks = []
    for ref in refs:
        km_ref = KMeans(n_clusters=k, random_state=random_state, n_init=10)
        km_ref.fit(ref)
        ref_Wks.append(km_ref.inertia_)

    gap = np.log(np.mean(ref_Wks)) - np.log(Wk)
    return float(gap)


def find_optimal_k(
    X: np.ndarray,
    k_min: int = 2,
    k_max: int = 10,
    random_state: int = 42,
) -> OptimalKResult:
    k_range = list(range(k_min, min(k_max + 1, len(X))))
    if len(k_range) < 2:
        k_range = [2]

    elbow = {}
    silhouettes = {}
    gaps = {}
    calinski = {}
    davies = {}

    for k in k_range:
        km = KMeans(n_clusters=k, random_state=random_state, n_init=10)
        labels = km.fit_predict(X)
        elbow[k] = float(km.inertia_)
        if len(set(labels)) > 1:
            silhouettes[k] = float(silhouette_score(X, labels))
            calinski[k] = float(calinski_harabasz_score(X, labels))
            davies[k] = float(davies_bouldin_score(X, labels))
        gaps[k] = _gap_statistic(X, k, random_state=random_state)

    # Elbow: max second derivative of inertia
    ks = sorted(elbow.keys())
    if len(ks) >= 3:
        inertias = [elbow[k] for k in ks]
        diffs = np.diff(inertias)
        diffs2 = np.diff(diffs)
        elbow_k = ks[np.argmin(diffs2) + 1] if len(diffs2) else ks[0]
    else:
        elbow_k = ks[0]

    sil_k = max(silhouettes, key=silhouettes.get) if silhouettes else k_min
    gap_k = max(gaps, key=gaps.get) if gaps else k_min
    ch_k = max(calinski, key=calinski.get) if calinski else k_min
    db_k = min(davies, key=davies.get) if davies else k_min

    votes = [elbow_k, sil_k, gap_k, ch_k, db_k]
    from collections import Counter
    vote_counts = Counter(votes)
    consensus = vote_counts.most_common(1)[0][0]
    agreement = vote_counts.most_common(1)[0][1] / len(votes)
    if agreement >= 0.6:
        agreement_label = "High"
    elif agreement >= 0.4:
        agreement_label = "Medium"
    else:
        agreement_label = "Low"

    alternatives = sorted(set(votes) - {consensus})

    return OptimalKResult(
        k_range=k_range,
        elbow_inertia=elbow,
        silhouette_scores=silhouettes,
        gap_scores=gaps,
        calinski_scores=calinski,
        davies_bouldin_scores=davies,
        recommendations={
            "elbow": elbow_k,
            "silhouette": sil_k,
            "gap_statistic": gap_k,
            "calinski_harabasz": ch_k,
            "davies_bouldin": db_k,
        },
        consensus_k=consensus,
        agreement_level=f"{agreement:.0%}",
        agreement_label=agreement_label,
        alternatives=alternatives,
    )
