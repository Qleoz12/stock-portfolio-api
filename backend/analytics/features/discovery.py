"""Auto-discover financial variables from DB schema, CSV headers, and code."""
from __future__ import annotations

import inspect
from typing import Any

import pandas as pd
from sqlalchemy import inspect as sa_inspect

from analytics.models.feature_definition import FeatureCategory, FeatureDefinition

# Columns that are identifiers, not clustering features
ID_COLUMNS = frozenset({
    "id", "stock_id", "ticker_yf", "symbol", "company_name", "exchange",
    "exchange_id", "sector", "industry", "currency", "isin", "created_at",
    "updated_at", "div_freq", "last_div_date", "next_earnings_date",
    "name", "broker", "description", "owner", "source", "qf_id", "short_name",
})

# Variables with data leakage risk for clustering
LEAKAGE_COLUMNS = frozenset({
    "model_value", "price_to_model_value", "fair_value", "price_to_fve",
    "correlation_pct", "verdict", "undervalued",
})

CATEGORY_MAP: dict[str, FeatureCategory] = {
    "last_close": FeatureCategory.PRICE,
    "day_change_pct": FeatureCategory.RETURNS,
    "max_drawdown": FeatureCategory.RISK,
    "ema_20": FeatureCategory.TECHNICAL,
    "ema_52": FeatureCategory.TECHNICAL,
    "ema_200": FeatureCategory.TECHNICAL,
    "macd": FeatureCategory.TECHNICAL,
    "macd_signal": FeatureCategory.TECHNICAL,
    "rsi_14": FeatureCategory.TECHNICAL,
    "dividend_ttm": FeatureCategory.DIVIDEND,
    "payments_ttm": FeatureCategory.DIVIDEND,
    "div_yield_ttm": FeatureCategory.DIVIDEND,
    "dividend_yield": FeatureCategory.DIVIDEND,
    "payout_ratio": FeatureCategory.DIVIDEND,
    "div_growth_5y_cagr": FeatureCategory.DIVIDEND,
    "dividend_score": FeatureCategory.DIVIDEND,
    "eps_estimate": FeatureCategory.FUNDAMENTALS,
    "reported_eps": FeatureCategory.FUNDAMENTALS,
    "surprise_pct": FeatureCategory.FUNDAMENTALS,
    "week_52_high": FeatureCategory.PRICE,
    "week_52_low": FeatureCategory.PRICE,
    "week_100_high": FeatureCategory.PRICE,
    "week_100_low": FeatureCategory.PRICE,
    "week_200_high": FeatureCategory.PRICE,
    "week_200_low": FeatureCategory.PRICE,
    "net_income_margin": FeatureCategory.FUNDAMENTALS,
    "return_on_assets": FeatureCategory.FUNDAMENTALS,
    "free_cash_flow": FeatureCategory.FUNDAMENTALS,
    "operating_cash_flow": FeatureCategory.FUNDAMENTALS,
    "fcf_yield": FeatureCategory.FUNDAMENTALS,
    "revenue": FeatureCategory.FUNDAMENTALS,
    "net_income": FeatureCategory.FUNDAMENTALS,
    "total_debt": FeatureCategory.FUNDAMENTALS,
    "debt_to_equity": FeatureCategory.FUNDAMENTALS,
    "health_score": FeatureCategory.RISK_ADJUSTED,
    "market_cap": FeatureCategory.MARKET,
    "volatility_1y": FeatureCategory.RISK,
    "beta": FeatureCategory.RISK,
    "annualized_return": FeatureCategory.RETURNS,
    "sharpe_ratio": FeatureCategory.RISK_ADJUSTED,
    "average_correlation": FeatureCategory.CORRELATION,
    "calmar_ratio": FeatureCategory.RISK_ADJUSTED,
    "open": FeatureCategory.PRICE,
    "high": FeatureCategory.PRICE,
    "low": FeatureCategory.PRICE,
    "close": FeatureCategory.PRICE,
    "volume": FeatureCategory.MARKET,
}


def _infer_category(name: str) -> FeatureCategory:
    if name in CATEGORY_MAP:
        return CATEGORY_MAP[name]
    lower = name.lower()
    if any(k in lower for k in ("return", "gain")):
        return FeatureCategory.RETURNS
    if any(k in lower for k in ("vol", "drawdown", "beta", "var")):
        return FeatureCategory.RISK
    if any(k in lower for k in ("div", "yield", "payout")):
        return FeatureCategory.DIVIDEND
    if any(k in lower for k in ("ema", "macd", "rsi")):
        return FeatureCategory.TECHNICAL
    if any(k in lower for k in ("corr", "covar")):
        return FeatureCategory.CORRELATION
    if any(k in lower for k in ("sharpe", "sortino", "calmar", "treynor")):
        return FeatureCategory.RISK_ADJUSTED
    return FeatureCategory.FUNDAMENTALS


def discover_from_sqlalchemy_model(model_class: type) -> list[FeatureDefinition]:
    """Discover features from a SQLAlchemy model's columns."""
    features: list[FeatureDefinition] = []
    mapper = sa_inspect(model_class)
    for col in mapper.columns:
        name = col.name
        if name in ID_COLUMNS:
            continue
        dtype = str(col.type)
        is_numeric = any(t in dtype.lower() for t in ("float", "integer", "numeric", "real"))
        if not is_numeric:
            continue
        features.append(
            FeatureDefinition(
                name=name,
                display_name=name.replace("_", " ").title(),
                category=_infer_category(name),
                dtype="float",
                source="db",
                found_in=f"models.{model_class.__name__}",
                clustering_enabled=name not in LEAKAGE_COLUMNS,
                default_selected=False,
                data_leakage_risk=name in LEAKAGE_COLUMNS,
            )
        )
    return features


def discover_from_dataframe(df: pd.DataFrame, source: str = "dataframe") -> list[FeatureDefinition]:
    """Discover numeric columns from a DataFrame."""
    features: list[FeatureDefinition] = []
    for col in df.columns:
        if col in ID_COLUMNS or col == "ticker":
            continue
        if not pd.api.types.is_numeric_dtype(df[col]):
            continue
        features.append(
            FeatureDefinition(
                name=str(col),
                display_name=str(col).replace("_", " ").title(),
                category=_infer_category(str(col)),
                dtype="float",
                source=source,
                found_in=source,
                clustering_enabled=str(col) not in LEAKAGE_COLUMNS,
            )
        )
    return features


def discover_all() -> list[FeatureDefinition]:
    """Discover all features from known sources in the project."""
    from models import Stock, StockFeature

    features: dict[str, FeatureDefinition] = {}

    for f in discover_from_sqlalchemy_model(Stock):
        if f.name not in ("market_cap",):
            features[f.name] = f
    features["market_cap"] = FeatureDefinition(
        name="market_cap",
        display_name="Market Cap",
        category=FeatureCategory.MARKET,
        source="db",
        found_in="models.Stock",
        clustering_enabled=True,
        scaling_method="log",
    )

    for f in discover_from_sqlalchemy_model(StockFeature):
        features[f.name] = f

    # Calculated features not in DB yet
    calculated = [
        ("annualized_return", "Annualized Return", FeatureCategory.RETURNS, "calculators.annualized_return"),
        ("volatility_1y", "Volatility 1Y", FeatureCategory.RISK, "calculators.volatility_1y"),
        ("beta", "Beta", FeatureCategory.RISK, "price_normalization"),
        ("sharpe_ratio", "Sharpe Ratio", FeatureCategory.RISK_ADJUSTED, "calculators.sharpe_ratio"),
        ("average_correlation", "Average Correlation", FeatureCategory.CORRELATION, "calculators.average_correlation"),
        ("calmar_ratio", "Calmar Ratio", FeatureCategory.RISK_ADJUSTED, "calculators.calmar_ratio"),
        ("dividend_score", "Dividend Score", FeatureCategory.DIVIDEND, "price_normalization"),
    ]
    for name, display, cat, src in calculated:
        if name not in features:
            features[name] = FeatureDefinition(
                name=name,
                display_name=display,
                category=cat,
                source="calculated",
                calculation_function=src,
                found_in=src,
                is_calculated=True,
                clustering_enabled=True,
            )

    return list(features.values())
