"""Data quality validation."""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

from analytics.models.quality_report import DataQualityReport, QualityStatus, ValidationIssue


def _file_hash(path: str) -> str:
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:16]
    except OSError:
        return ""


def validate_dataset(
    df: pd.DataFrame,
    dataset_id: str = "analytic",
    source: str = "db",
    min_assets: int = 5,
    max_missing_pct: float = 0.50,
) -> DataQualityReport:
    """Validate a feature dataset and return quality report."""
    issues: list[ValidationIssue] = []
    recommendations: list[str] = []

    if df.empty:
        return DataQualityReport(
            dataset_id=dataset_id,
            source=source,
            status=QualityStatus.INSUFFICIENT_DATA,
            issues=[ValidationIssue(
                severity="error", category="structure",
                message="Dataset is empty",
            )],
            recommendations=["Add tickers to the universe or download OHLCV data."],
        )

    row_count = len(df)
    col_count = len(df.columns)
    asset_count = row_count

    if asset_count < min_assets:
        issues.append(ValidationIssue(
            severity="error", category="assets",
            message=f"Only {asset_count} assets (minimum {min_assets})",
            affected_rows=asset_count,
        ))

    missing_pct = {}
    constant_cols = []
    numeric_cols = df.select_dtypes(include=[np.number]).columns

    for col in numeric_cols:
        miss = float(df[col].isna().mean())
        missing_pct[str(col)] = round(miss * 100, 2)
        if miss > max_missing_pct:
            issues.append(ValidationIssue(
                severity="warning", category="missing",
                message=f"Column '{col}' has {miss:.0%} missing values",
                column=str(col),
            ))
        nunique = df[col].nunique(dropna=True)
        if nunique <= 1:
            constant_cols.append(str(col))
            issues.append(ValidationIssue(
                severity="warning", category="variance",
                message=f"Column '{col}' is constant or near-constant",
                column=str(col),
            ))

    dup_count = int(df.index.duplicated().sum()) if df.index.name else 0
    if dup_count:
        issues.append(ValidationIssue(
            severity="error", category="duplicates",
            message=f"{dup_count} duplicate index values",
            affected_rows=dup_count,
        ))

    # Outlier detection (IQR)
    for col in numeric_cols[:20]:
        s = df[col].dropna()
        if len(s) < 5:
            continue
        q1, q3 = s.quantile(0.25), s.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue
        outliers = ((s < q1 - 3 * iqr) | (s > q3 + 3 * iqr)).sum()
        if outliers > 0:
            issues.append(ValidationIssue(
                severity="info", category="outliers",
                message=f"Column '{col}' has {outliers} extreme outliers (3×IQR)",
                column=str(col),
                affected_rows=int(outliers),
            ))

    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]

    if errors:
        status = QualityStatus.INVALID
    elif asset_count < min_assets:
        status = QualityStatus.INSUFFICIENT_DATA
    elif warnings:
        status = QualityStatus.VALID_WITH_WARNINGS
        recommendations.append("Review warnings before clustering; imputation will be applied.")
    else:
        status = QualityStatus.VALID

    if constant_cols:
        recommendations.append(f"Exclude constant columns: {', '.join(constant_cols[:5])}")

    return DataQualityReport(
        dataset_id=dataset_id,
        source=source,
        status=status,
        row_count=row_count,
        column_count=col_count,
        asset_count=asset_count,
        missing_pct=missing_pct,
        constant_columns=constant_cols,
        duplicate_rows=dup_count,
        issues=issues,
        recommendations=recommendations,
        checked_at=datetime.utcnow(),
    )
