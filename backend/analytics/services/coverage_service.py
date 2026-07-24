"""Universe coverage service."""
from __future__ import annotations

from sqlalchemy.orm import Session

from analytics.data.loaders import build_analytic_dataset
from analytics.features.transformations import apply_transformations
from analytics.preprocessing.dimensionality import check_dimensionality
from analytics.services.universe_service import UniverseService
from analytics.validation.universe_coverage import analyze_universe_coverage
from analytics.features.registry import get_registry


class CoverageService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_coverage(
        self,
        universe_id: str,
        period_days: int = 365,
        feature_profile: str = "ALL_CLUSTERING_ELIGIBLE_FEATURES",
        selected_features: list[str] | None = None,
    ) -> dict:
        usvc = UniverseService(self.db)
        tickers = usvc.resolve_tickers(universe_id)
        registry = get_registry()

        df = build_analytic_dataset(self.db, tickers, period_days)
        if not df.empty:
            df = apply_transformations(df)

        feature_cols = selected_features or registry.resolve_profile_features(
            feature_profile,
            available_columns=set(df.columns) if not df.empty else None,
            df=df if not df.empty else None,
        )

        report = analyze_universe_coverage(
            self.db, tickers, universe_id, feature_cols=feature_cols
        )
        dim = check_dimensionality(
            report.valid_count or len(df),
            len(feature_cols),
        )

        return {
            "coverage": {
                "universe_id": report.universe_id,
                "requested_count": report.requested_count,
                "found_count": report.found_count,
                "valid_count": report.valid_count,
                "excluded_count": report.excluded_count,
                "coverage_pct": report.coverage_pct,
                "overall_status": report.overall_status,
                "missing_tickers": report.missing_tickers,
                "tickers": [
                    {
                        "ticker": t.ticker,
                        "status": t.status,
                        "reason": t.reason,
                        "company_name": t.company_name,
                        "sector": t.sector,
                        "missing_features": t.missing_features,
                        "in_database": t.in_database,
                    }
                    for t in report.tickers
                ],
            },
            "dimensionality": {
                "n_assets": dim.n_assets,
                "n_features": dim.n_features,
                "recommended_max": dim.recommended_max,
                "is_high": dim.is_high,
                "message": dim.message,
                "actions": dim.actions,
            },
            "selected_features": feature_cols,
        }
