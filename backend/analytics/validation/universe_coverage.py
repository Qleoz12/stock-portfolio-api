"""Universe coverage analysis per ticker."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from models import Stock, StockFeature


@dataclass
class TickerCoverage:
    ticker: str
    status: str  # valid, valid_with_warning, missing_data, insufficient_history, invalid_ticker, excluded, unavailable
    reason: str
    company_name: str = ""
    sector: str = ""
    missing_features: list[str] = field(default_factory=list)
    available_period_days: Optional[int] = None
    in_database: bool = False


@dataclass
class UniverseCoverageReport:
    universe_id: str
    requested_count: int
    found_count: int
    valid_count: int
    excluded_count: int
    coverage_pct: float
    overall_status: str
    tickers: list[TickerCoverage] = field(default_factory=list)
    missing_tickers: list[str] = field(default_factory=list)


def analyze_universe_coverage(
    db: Session,
    requested_tickers: list[str],
    universe_id: str = "custom",
    feature_cols: Optional[list[str]] = None,
    min_history_days: int = 60,
) -> UniverseCoverageReport:
    """Compare requested universe vs DB availability."""
    feature_cols = feature_cols or []
    stocks = {
        s.ticker_yf: s
        for s in db.query(Stock).filter(Stock.ticker_yf.in_(requested_tickers)).all()
    }
    features = {}
    if stocks:
        feats = (
            db.query(StockFeature)
            .filter(StockFeature.stock_id.in_([s.id for s in stocks.values()]))
            .all()
        )
        features = {f.stock_id: f for f in feats}

    rows: list[TickerCoverage] = []
    valid_count = 0

    for ticker in requested_tickers:
        stock = stocks.get(ticker)
        if not stock:
            rows.append(TickerCoverage(
                ticker=ticker,
                status="unavailable",
                reason="Ticker not found in local database",
                in_database=False,
            ))
            continue

        feat = features.get(stock.id)
        missing_feats: list[str] = []
        if feature_cols and feat:
            for col in feature_cols:
                val = getattr(feat, col, None)
                if val is None or (isinstance(val, float) and pd.isna(val)):
                    missing_feats.append(col)

        status = "valid"
        reason = "Available in database with features"
        if not feat or feat.last_close is None:
            status = "missing_data"
            reason = "No feature record or last_close missing"
        elif missing_feats and len(missing_feats) > len(feature_cols) * 0.5:
            status = "missing_data"
            reason = f"More than 50% of selected features missing ({len(missing_feats)})"
        elif missing_feats:
            status = "valid_with_warning"
            reason = f"Partial feature coverage ({len(missing_feats)} missing)"

        if status in ("valid", "valid_with_warning"):
            valid_count += 1

        rows.append(TickerCoverage(
            ticker=ticker,
            status=status,
            reason=reason,
            company_name=stock.company_name or "",
            sector=stock.sector or "",
            missing_features=missing_feats[:10],
            in_database=True,
        ))

    found = len([r for r in rows if r.in_database])
    excluded = len(requested_tickers) - valid_count
    coverage = (valid_count / len(requested_tickers) * 100) if requested_tickers else 0.0

    if coverage >= 95:
        overall = "valid"
    elif coverage >= 70:
        overall = "valid_with_warnings"
    elif coverage >= 50:
        overall = "needs_cleaning"
    else:
        overall = "insufficient_data"

    return UniverseCoverageReport(
        universe_id=universe_id,
        requested_count=len(requested_tickers),
        found_count=found,
        valid_count=valid_count,
        excluded_count=excluded,
        coverage_pct=round(coverage, 1),
        overall_status=overall,
        tickers=rows,
        missing_tickers=[r.ticker for r in rows if not r.in_database],
    )
