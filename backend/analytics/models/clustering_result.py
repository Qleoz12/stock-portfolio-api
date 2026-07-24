"""Clustering result models."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ClusteringMode(str, Enum):
    FEATURE = "feature"
    CORRELATION = "correlation"


class ClusterAssignment(BaseModel):
    ticker: str
    cluster_id: int
    silhouette: Optional[float] = None
    distance_to_center: Optional[float] = None
    is_representative: bool = False


class AlgorithmResult(BaseModel):
    algorithm: str
    linkage: Optional[str] = None
    k: int
    assignments: list[ClusterAssignment] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
    cluster_sizes: dict[int, int] = Field(default_factory=dict)
    negative_silhouette_count: int = 0


class ClusteringRunResult(BaseModel):
    run_id: str
    universe_id: str
    mode: ClusteringMode
    features_used: list[str] = Field(default_factory=list)
    k_recommended: int = 3
    k_consensus: dict[str, int] = Field(default_factory=dict)
    hopkins_statistic: Optional[float] = None
    tendency_warning: Optional[str] = None
    algorithms: list[AlgorithmResult] = Field(default_factory=list)
    best_algorithm: Optional[str] = None
    best_algorithm_reason: str = ""
    lineage: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AnalyzeRequest(BaseModel):
    universe_id: str = "dow30"
    tickers: Optional[list[str]] = None
    mode: ClusteringMode = ClusteringMode.FEATURE
    feature_profile: str = "ALL_CLUSTERING_ELIGIBLE_FEATURES"
    features: Optional[list[str]] = None
    period_days: int = 365
    k_min: int = 2
    k_max: int = 10
    random_seed: int = 42
    benchmark: str = "^GSPC"
    # Correlation mode params
    correlation_frequency: str = "daily"
    correlation_method: str = "pearson"
    correlation_distance: str = "sqrt_half"
    min_observations: int = 60
