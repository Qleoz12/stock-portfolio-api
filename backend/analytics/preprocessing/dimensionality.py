"""Dimensionality warnings for clustering."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DimensionalityWarning:
    n_assets: int
    n_features: int
    recommended_max: int
    is_high: bool
    message: str
    actions: list[str]


def check_dimensionality(n_assets: int, n_features: int) -> DimensionalityWarning:
    """Rule: features <= min(10, floor(n_assets / 3))."""
    if n_assets < 3:
        recommended = 2
    else:
        recommended = min(10, max(2, n_assets // 3))

    is_high = n_features > recommended
    msg = ""
    actions: list[str] = []
    if is_high:
        msg = (
            f"High dimensionality: {n_assets} assets and {n_features} selected variables. "
            f"The number of features is too large relative to observations. "
            f"Results may be unstable or driven by noise. Recommended maximum: {recommended}."
        )
        actions = [
            "Apply recommended features",
            "Use PCA",
            "Choose a profile",
            "Continue anyway",
        ]
    else:
        msg = f"Dimensionality OK: {n_features} features for {n_assets} assets (max recommended: {recommended})."

    return DimensionalityWarning(
        n_assets=n_assets,
        n_features=n_features,
        recommended_max=recommended,
        is_high=is_high,
        message=msg,
        actions=actions,
    )
