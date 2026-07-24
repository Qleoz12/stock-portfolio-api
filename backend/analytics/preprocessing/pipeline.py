"""Preprocessing pipeline for clustering."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler, RobustScaler, StandardScaler


@dataclass
class PreprocessResult:
    X: np.ndarray
    feature_names: list[str]
    tickers: list[str]
    scaler_name: str
    transformations: list[str] = field(default_factory=list)
    rows_dropped: int = 0
    values_imputed: int = 0
    original_df: Optional[pd.DataFrame] = None
    scaled_df: Optional[pd.DataFrame] = None


def winsorize_series(s: pd.Series, lower: float = 0.01, upper: float = 0.99) -> pd.Series:
    lo, hi = s.quantile(lower), s.quantile(upper)
    return s.clip(lo, hi)


def preprocess_features(
    df: pd.DataFrame,
    feature_cols: list[str],
    scaler: str = "standard",
    winsorize: bool = True,
    drop_na_rows: bool = False,
    impute_strategy: str = "median",
) -> PreprocessResult:
    """Clean, impute, winsorize, and scale feature matrix."""
    transformations: list[str] = []
    sub = df[feature_cols].copy()
    rows_dropped = 0
    values_imputed = 0

    # Drop rows with too many missing
    if drop_na_rows:
        before = len(sub)
        sub = sub.dropna()
        rows_dropped = before - len(sub)
        transformations.append(f"dropped {rows_dropped} rows with NaN")

    # Impute
    for col in sub.columns:
        n_missing = int(sub[col].isna().sum())
        if n_missing == 0:
            continue
        if impute_strategy == "median":
            fill = sub[col].median()
        elif impute_strategy == "mean":
            fill = sub[col].mean()
        else:
            fill = 0
        sub[col] = sub[col].fillna(fill)
        values_imputed += n_missing
    if values_imputed:
        transformations.append(f"imputed {values_imputed} values ({impute_strategy})")

    # Winsorize outliers
    if winsorize:
        for col in sub.columns:
            sub[col] = winsorize_series(sub[col])
        transformations.append("winsorized at 1%/99%")

    tickers = list(sub.index)
    X_raw = sub.values.astype(float)

    if scaler == "robust":
        sc = RobustScaler()
    elif scaler == "minmax":
        sc = MinMaxScaler()
    else:
        sc = StandardScaler()
    X = sc.fit_transform(X_raw)
    transformations.append(f"scaled with {scaler}")

    scaled_df = pd.DataFrame(X, index=tickers, columns=feature_cols)

    return PreprocessResult(
        X=X,
        feature_names=feature_cols,
        tickers=tickers,
        scaler_name=scaler,
        transformations=transformations,
        rows_dropped=rows_dropped,
        values_imputed=values_imputed,
        original_df=df.loc[tickers, feature_cols] if tickers else None,
        scaled_df=scaled_df,
    )
