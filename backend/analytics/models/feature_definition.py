"""Feature definition models."""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class FeatureCategory(str, Enum):
    IDENTIFICATION = "identification"
    PRICE = "price"
    RETURNS = "returns"
    RISK = "risk"
    RISK_ADJUSTED = "risk_adjusted"
    CORRELATION = "correlation"
    MARKET = "market"
    FUNDAMENTALS = "fundamentals"
    TECHNICAL = "technical"
    DIVIDEND = "dividend"
    PORTFOLIO = "portfolio"
    VALUATION = "valuation"
    CLUSTERING = "clustering"


class FeatureDefinition(BaseModel):
    name: str
    display_name: str
    category: FeatureCategory
    description: str = ""
    dtype: str = "float"
    unit: str = ""
    source: str = "db"
    calculation_function: Optional[str] = None
    required_columns: list[str] = Field(default_factory=list)
    validation_rules: dict[str, Any] = Field(default_factory=dict)
    clustering_enabled: bool = True
    default_selected: bool = False
    scaling_method: str = "standard"
    missing_value_strategy: str = "median"
    allows_negative: bool = True
    requires_normalization: bool = True
    data_leakage_risk: bool = False
    is_calculated: bool = False
    found_in: str = ""


class FeatureProfile(BaseModel):
    name: str
    display_name: str
    description: str = ""
    feature_names: list[str] = Field(default_factory=list)
