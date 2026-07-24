"""Financial feature transformations for clustering."""
from __future__ import annotations

import numpy as np
import pandas as pd

# Raw columns that must NOT enter clustering without transformation
RAW_PRICE_COLS = frozenset({
    "last_close", "ema_20", "ema_52", "ema_200",
    "week_52_high", "week_52_low", "week_100_high", "week_100_low",
    "week_200_high", "week_200_low", "open", "high", "low", "close",
})

RAW_SIZE_COLS = frozenset({
    "market_cap", "revenue", "net_income", "free_cash_flow", "total_debt",
    "operating_cash_flow",
})

TRANSFORMED_FEATURES: dict[str, dict] = {
    "price_to_ema20": {"requires": ["last_close", "ema_20"], "formula": "last_close/ema_20 - 1"},
    "price_to_ema52": {"requires": ["last_close", "ema_52"], "formula": "last_close/ema_52 - 1"},
    "price_to_ema200": {"requires": ["last_close", "ema_200"], "formula": "last_close/ema_200 - 1"},
    "distance_from_52w_high": {"requires": ["last_close", "week_52_high"], "formula": "last_close/week_52_high - 1"},
    "distance_from_52w_low": {"requires": ["last_close", "week_52_low"], "formula": "last_close/week_52_low - 1"},
    "normalized_macd": {"requires": ["macd", "last_close"], "formula": "macd/last_close"},
    "normalized_macd_signal": {"requires": ["macd_signal", "last_close"], "formula": "macd_signal/last_close"},
    "log_market_cap": {"requires": ["market_cap"], "formula": "log(market_cap)"},
    "log_revenue": {"requires": ["revenue"], "formula": "log(revenue)"},
    "log_total_debt": {"requires": ["total_debt"], "formula": "log(total_debt)"},
    "fcf_yield": {"requires": ["free_cash_flow", "market_cap"], "formula": "fcf/market_cap"},
}


def _safe_ratio(num: pd.Series, den: pd.Series) -> pd.Series:
    with np.errstate(divide="ignore", invalid="ignore"):
        r = num / den.replace(0, np.nan) - 1.0
    return r.replace([np.inf, -np.inf], np.nan)


def apply_transformations(df: pd.DataFrame) -> pd.DataFrame:
    """Add transformed ratio/log columns to dataframe."""
    out = df.copy()
    lc = out.get("last_close")

    if lc is not None:
        for ema_col, name in [("ema_20", "price_to_ema20"), ("ema_52", "price_to_ema52"), ("ema_200", "price_to_ema200")]:
            if ema_col in out.columns:
                out[name] = _safe_ratio(lc, out[ema_col])
        if "week_52_high" in out.columns:
            out["distance_from_52w_high"] = _safe_ratio(lc, out["week_52_high"])
        if "week_52_low" in out.columns:
            out["distance_from_52w_low"] = _safe_ratio(lc, out["week_52_low"])
        if "macd" in out.columns:
            out["normalized_macd"] = out["macd"] / lc.replace(0, np.nan)
        if "macd_signal" in out.columns:
            out["normalized_macd_signal"] = out["macd_signal"] / lc.replace(0, np.nan)

    for col, name in [("market_cap", "log_market_cap"), ("revenue", "log_revenue"), ("total_debt", "log_total_debt")]:
        if col in out.columns:
            s = out[col].astype(float)
            out[name] = np.log(s.clip(lower=1))

    if "free_cash_flow" in out.columns and "market_cap" in out.columns:
        out["fcf_yield_calc"] = out["free_cash_flow"] / out["market_cap"].replace(0, np.nan)

    return out


def is_clustering_eligible(column: str, transformed: bool = False) -> tuple[bool, str]:
    """Return (eligible, reason)."""
    if column in ("ticker", "symbol", "company_name", "sector", "industry", "exchange", "currency"):
        return False, "Metadata column"
    if column in RAW_PRICE_COLS and not transformed:
        return False, "Absolute price level — use ratio transformation"
    if column in RAW_SIZE_COLS and not column.startswith("log_"):
        return False, "Absolute size — use log or ratio"
    return True, "Eligible for clustering"
