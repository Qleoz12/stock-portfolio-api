"""Clustering algorithms: hierarchical, k-means, k-medoids."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import pdist, squareform
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_samples, silhouette_score

try:
    from sklearn_extra.cluster import KMedoids
    HAS_KMEDOIDS = True
except (ImportError, ValueError):
    HAS_KMEDOIDS = False


@dataclass
class ClusterOutput:
    labels: np.ndarray
    algorithm: str
    linkage_method: Optional[str] = None
    centroids: Optional[np.ndarray] = None
    medoids: Optional[np.ndarray] = None
    linkage_matrix: Optional[np.ndarray] = None


def hierarchical_cluster(
    X: np.ndarray,
    k: int,
    method: str = "ward",
    metric: str = "euclidean",
) -> ClusterOutput:
    if metric == "precomputed":
        condensed = X[np.triu_indices(len(X), k=1)]
    else:
        condensed = pdist(X, metric=metric)
    Z = linkage(condensed, method=method)
    labels = fcluster(Z, t=k, criterion="maxclust") - 1
    return ClusterOutput(
        labels=labels.astype(int),
        algorithm="hierarchical",
        linkage_method=method,
        linkage_matrix=Z,
    )


def kmeans_cluster(X: np.ndarray, k: int, random_state: int = 42) -> ClusterOutput:
    km = KMeans(n_clusters=k, random_state=random_state, n_init=10)
    labels = km.fit_predict(X)
    return ClusterOutput(
        labels=labels,
        algorithm="kmeans",
        centroids=km.cluster_centers_,
    )


def kmedoids_cluster(
    X: np.ndarray,
    k: int,
    metric: str = "euclidean",
    random_state: int = 42,
) -> ClusterOutput:
    if not HAS_KMEDOIDS:
        out = kmeans_cluster(X, k, random_state)
        out.algorithm = "pam_fallback_kmeans"
        return out
    km = KMedoids(n_clusters=k, metric=metric, random_state=random_state, init="k-medoids++")
    labels = km.fit_predict(X)
    return ClusterOutput(
        labels=labels,
        algorithm="pam",
        medoids=km.cluster_centers_,
    )


def run_all_algorithms(
    X: np.ndarray,
    k: int,
    dist_matrix: Optional[np.ndarray] = None,
    random_state: int = 42,
) -> list[ClusterOutput]:
    results = []
    for method in ("ward", "complete", "average"):
        try:
            results.append(hierarchical_cluster(X, k, method=method))
        except Exception:
            pass
    results.append(kmeans_cluster(X, k, random_state))
    pam_out = kmedoids_cluster(X, k, random_state=random_state)
    if pam_out.algorithm != "pam_fallback_kmeans":
        results.append(pam_out)
    else:
        pam_out.algorithm = "kmedoids_unavailable"
        pam_out.linkage_method = "fallback_kmeans"
        results.append(pam_out)
    if dist_matrix is not None:
        try:
            out = hierarchical_cluster(dist_matrix, k, method="average", metric="precomputed")
            out.linkage_method = "average_precomputed"
            results.append(out)
        except Exception:
            pass
    return results
