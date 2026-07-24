"""Dataset explorer service for grid views."""
from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from analytics.data.loaders import build_analytic_dataset, load_ohlcv_wide
from analytics.data.returns_matrix import align_returns
from analytics.features.registry import get_registry
from analytics.features.transformations import apply_transformations
from analytics.preprocessing.pipeline import preprocess_features
from analytics.services.universe_service import UniverseService
from analytics.clustering.correlation_pipeline import (
    CorrelationConfig,
    build_returns_matrix,
    correlation_distance_matrix,
)
from analytics.utils.json_safe import sanitize_for_json


class DatasetService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_dataset(
        self,
        universe_id: str,
        view: str = "raw",
        period_days: int = 365,
        feature_profile: str = "ALL_CLUSTERING_ELIGIBLE_FEATURES",
        selected_features: list[str] | None = None,
        benchmark: str = "^GSPC",
        correlation_config: CorrelationConfig | None = None,
    ) -> dict[str, Any]:
        usvc = UniverseService(self.db)
        tickers = usvc.resolve_tickers(universe_id)
        registry = get_registry()

        df = build_analytic_dataset(self.db, tickers, period_days, benchmark)
        if df.empty:
            return {"view": view, "rows": [], "columns": [], "row_count": 0}

        df = apply_transformations(df)
        feature_cols = selected_features or registry.resolve_profile_features(
            feature_profile,
            available_columns=set(df.columns),
            df=df,
        )

        if view in ("returns", "correlation", "distance"):
            return self._correlation_view(tickers, period_days, view, correlation_config)

        if view == "scaled":
            sub = df.loc[df.index.intersection(tickers), feature_cols]
            prep = preprocess_features(sub, feature_cols)
            scaled = pd.DataFrame(prep.X, index=prep.tickers, columns=feature_cols)
            scaled = scaled.reset_index().rename(columns={"index": "ticker"})
            return self._pack_df(scaled, view, feature_cols)

        if view == "clean":
            sub = df.loc[df.index.intersection(tickers), feature_cols]
            prep = preprocess_features(sub, feature_cols)
            clean = sub.loc[prep.tickers]
            clean = clean.reset_index().rename(columns={"index": "ticker"})
            return self._pack_df(clean, view, feature_cols)

        if view == "validated":
            sub = df.loc[df.index.intersection(tickers)]
            sub = sub.reset_index().rename(columns={"index": "ticker"})
            return self._pack_df(sub, view, list(sub.columns))

        # raw (default)
        sub = df.loc[df.index.intersection(tickers)]
        sub = sub.reset_index().rename(columns={"index": "ticker"})
        return self._pack_df(sub, view, list(sub.columns))

    def _correlation_view(
        self,
        tickers: list[str],
        period_days: int,
        view: str,
        config: CorrelationConfig | None,
    ) -> dict[str, Any]:
        cfg = config or CorrelationConfig(lookback_days=period_days)
        prices_df, _ = load_ohlcv_wide(self.db, tickers, cfg.lookback_days)
        if prices_df.empty:
            return {"view": view, "rows": [], "columns": [], "row_count": 0}

        returns_df = build_returns_matrix(prices_df, cfg.frequency)
        returns_df = align_returns(returns_df)
        corr, dist, shared = correlation_distance_matrix(
            returns_df, cfg.method, cfg.distance_method
        )

        if view == "returns":
            out = returns_df.reset_index().rename(columns={"index": "date"})
            return self._pack_df(out, view, list(returns_df.columns))

        mat = corr if view == "correlation" else dist
        rows = []
        for ticker in mat.index:
            row = {"ticker": ticker}
            for col in mat.columns:
                row[col] = mat.loc[ticker, col]
            rows.append(row)
        return sanitize_for_json({
            "view": view,
            "rows": rows,
            "columns": ["ticker"] + list(mat.columns),
            "row_count": len(rows),
            "matrix_type": view,
        })

    def _pack_df(self, df: pd.DataFrame, view: str, feature_cols: list[str]) -> dict[str, Any]:
        return sanitize_for_json({
            "view": view,
            "rows": df.to_dict(orient="records"),
            "columns": list(df.columns),
            "row_count": len(df),
            "feature_cols": feature_cols,
        })
