"""Data quality report models."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class QualityStatus(str, Enum):
    VALID = "valid"
    VALID_WITH_WARNINGS = "valid_with_warnings"
    NEEDS_CLEANING = "needs_cleaning"
    INVALID = "invalid"
    INSUFFICIENT_DATA = "insufficient_data"


class ValidationIssue(BaseModel):
    severity: str  # error, warning, info
    category: str
    message: str
    column: Optional[str] = None
    affected_rows: int = 0
    sample_values: list[Any] = Field(default_factory=list)


class DataQualityReport(BaseModel):
    dataset_id: str
    source: str
    status: QualityStatus
    row_count: int = 0
    column_count: int = 0
    asset_count: int = 0
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    missing_pct: dict[str, float] = Field(default_factory=dict)
    constant_columns: list[str] = Field(default_factory=list)
    duplicate_rows: int = 0
    issues: list[ValidationIssue] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    checked_at: datetime = Field(default_factory=datetime.utcnow)


class DatasetLineage(BaseModel):
    source: str
    original_file: Optional[str] = None
    loaded_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    file_hash: Optional[str] = None
    transformations: list[str] = Field(default_factory=list)
    variables_used: list[str] = Field(default_factory=list)
    rows_removed: int = 0
    values_imputed: int = 0
    normalization_method: Optional[str] = None
    time_window: Optional[str] = None
    frequency: Optional[str] = None
    benchmark: Optional[str] = None
    pipeline_version: str = "1.0.0"
    random_seed: Optional[int] = None
