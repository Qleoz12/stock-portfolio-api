"""Financial feature calculators."""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


def annualized_return(returns: pd.Series, periods_per_year: int = 252) -> Optional[float]:
    """Compound annualized return from daily returns."""
    if returns is None or returns.dropna().empty:
        return None
    r = returns.dropna()
    total = (1 + r).prod() - 1
    n = len(r)
    if n < 2:
        return None
    years = n / periods_per_year
    if years <= 0:
        return None
    return float((1 + total) ** (1 / years) - 1)


def volatility_1y(returns: pd.Series, periods_per_year: int = 252) -> Optional[float]:
    if returns is None or returns.dropna().empty:
        return None
    return float(returns.dropna().std() * np.sqrt(periods_per_year))


def sharpe_ratio(
    returns: pd.Series,
    risk_free: float = 0.0,
    periods_per_year: int = 252,
) -> Optional[float]:
    vol = volatility_1y(returns, periods_per_year)
    ann_ret = annualized_return(returns, periods_per_year)
    if vol is None or ann_ret is None or vol == 0:
        return None
    return float((ann_ret - risk_free) / vol)


def max_drawdown_from_prices(prices: pd.Series) -> Optional[float]:
    if prices is None or prices.dropna().empty:
        return None
    p = prices.dropna()
    peak = p.cummax()
    dd = (p - peak) / peak
    return float(dd.min())


def calmar_ratio(returns: pd.Series, prices: pd.Series) -> Optional[float]:
    ann = annualized_return(returns)
    mdd = max_drawdown_from_prices(prices)
    if ann is None or mdd is None or mdd == 0:
        return None
    return float(ann / abs(mdd))


def average_correlation(corr_matrix: pd.DataFrame, ticker: str) -> Optional[float]:
    """Mean pairwise correlation excluding self."""
    if ticker not in corr_matrix.columns:
        return None
    row = corr_matrix[ticker].drop(ticker, errors="ignore")
    row = row.dropna()
    if row.empty:
        return None
    return float(row.mean())


def compute_features_for_universe(
    returns_df: pd.DataFrame,
    prices_df: pd.DataFrame,
    beta_map: Optional[dict[str, float]] = None,
) -> pd.DataFrame:
    """Build per-asset feature row from aligned returns/prices."""
    corr = returns_df.corr()
    rows = []
    for ticker in returns_df.columns:
        ret = returns_df[ticker]
        px = prices_df[ticker] if ticker in prices_df.columns else None
        row = {
            "ticker": ticker,
            "annualized_return": annualized_return(ret),
            "volatility_1y": volatility_1y(ret),
            "sharpe_ratio": sharpe_ratio(ret),
            "average_correlation": average_correlation(corr, ticker),
        }
        if px is not None:
            row["max_drawdown"] = max_drawdown_from_prices(px)
            row["calmar_ratio"] = calmar_ratio(ret, px)
        if beta_map and ticker in beta_map:
            row["beta"] = beta_map[ticker]
        rows.append(row)
    return pd.DataFrame(rows).set_index("ticker")
