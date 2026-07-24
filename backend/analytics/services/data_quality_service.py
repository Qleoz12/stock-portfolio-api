"""Data quality service."""
from __future__ import annotations

import pandas as pd
from sqlalchemy.orm import Session

from analytics.data.loaders import build_analytic_dataset
from analytics.validation.quality_report import validate_dataset
from analytics.models.quality_report import DataQualityReport


class DataQualityService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def validate_universe(
        self,
        tickers: list[str],
        period_days: int = 365,
        dataset_id: str = "universe",
    ) -> tuple[DataQualityReport, pd.DataFrame]:
        df = build_analytic_dataset(self.db, tickers, period_days)
        numeric = df.select_dtypes(include="number")
        report = validate_dataset(numeric, dataset_id=dataset_id, source="db")
        return report, df
