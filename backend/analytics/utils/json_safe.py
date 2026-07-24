"""JSON-safe serialization helpers for analytics API responses."""
from __future__ import annotations

import math
from datetime import date, datetime
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd


def _sanitize_scalar(value: Any, *, decimals: int) -> Any:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer, int)) and not isinstance(value, bool):
        return int(value)
    if isinstance(value, (np.floating, float)):
        v = float(value)
        if not math.isfinite(v):
            return None
        return round(v, decimals)
    if isinstance(value, (np.ndarray,)):
        return sanitize_for_json(value.tolist(), decimals=decimals)
    if pd.isna(value):
        return None
    return value


def sanitize_for_json(obj: Any, *, decimals: int = 6) -> Any:
    """Recursively convert NaN/Inf to None; round finite floats."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {str(k): sanitize_for_json(v, decimals=decimals) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_for_json(v, decimals=decimals) for v in obj]
    if isinstance(obj, np.ndarray):
        return sanitize_for_json(obj.tolist(), decimals=decimals)
    if isinstance(obj, pd.Series):
        return sanitize_for_json(obj.tolist(), decimals=decimals)
    if isinstance(obj, pd.DataFrame):
        return sanitize_for_json(obj.to_dict(orient="records"), decimals=decimals)
    return _sanitize_scalar(obj, decimals=decimals)
