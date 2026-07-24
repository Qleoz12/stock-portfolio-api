"""Correlation-based clustering pipeline."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from analytics.data.returns_matrix import align_returns, correlation_matrix


@dataclass
class CorrelationConfig:
    frequency: str = "daily"  # daily, weekly, monthly
    method: str = "pearson"  # pearson, spearman, kendall
    lookback_days: int = 365
    min_observations: int = 60
    min_coverage: float = 0.5
    distance_method: str = "sqrt_half"  # sqrt_half or one_minus


def build_returns_matrix(
    prices_df: pd.DataFrame,
    frequency: str = "daily",
) -> pd.DataFrame:
    if prices_df.empty:
        return pd.DataFrame()
    if frequency == "weekly":
        px = prices_df.resample("W").last()
    elif frequency == "monthly":
        px = prices_df.resample("ME").last()
    else:
        px = prices_df
    return px.pct_change(fill_method=None).dropna(how="all")


def correlation_distance_matrix(
    returns_df: pd.DataFrame,
    method: str = "pearson",
    distance_method: str = "sqrt_half",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (correlation, distance, shared_obs_count)."""
    corr = returns_df.corr(method=method)
    n = len(returns_df)
    shared = pd.DataFrame(
        returns_df.notna().T @ returns_df.notna(),
        index=corr.index,
        columns=corr.columns,
    )
    if distance_method == "sqrt_half":
        dist = np.sqrt(0.5 * (1 - corr))
    else:
        dist = 1.0 - corr
    np.fill_diagonal(dist.values, 0.0)
    return corr, dist, shared
