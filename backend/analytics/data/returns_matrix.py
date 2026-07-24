"""Aligned returns and correlation matrices."""
from __future__ import annotations

import numpy as np
import pandas as pd


def correlation_matrix(returns_df: pd.DataFrame) -> pd.DataFrame:
    """Pearson correlation of aligned returns."""
    return returns_df.corr(method="pearson")


def distance_from_correlation(corr: pd.DataFrame, absolute: bool = False) -> pd.DataFrame:
    """Distance = 1 - correlation (or 1 - |correlation|)."""
    c = corr.abs() if absolute else corr
    dist = 1.0 - c
    np.fill_diagonal(dist.values, 0.0)
    return dist


def align_returns(
    returns_df: pd.DataFrame,
    min_coverage: float = 0.5,
) -> pd.DataFrame:
    """Drop tickers with insufficient data coverage."""
    if returns_df.empty:
        return returns_df
    coverage = returns_df.notna().sum() / len(returns_df)
    valid = coverage[coverage >= min_coverage].index.tolist()
    return returns_df[valid].dropna(how="any")
