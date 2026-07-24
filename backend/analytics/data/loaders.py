"""Load data from DB, universes, CSV files."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from analytics.features.calculators import compute_features_for_universe
from models import Exchange, Stock, StockFeature, StockOHLCV

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def load_constituents_file(name: str) -> list[str]:
    path = DATA_DIR / name
    if not path.exists():
        return []
    return [
        ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.startswith("#")
    ]


def load_universe_tickers(universe_id: str, db: Session) -> list[str]:
    if universe_id == "dow30":
        return load_constituents_file("dow30_constituents.txt")
    if universe_id == "sp500":
        return load_constituents_file("sp500_constituents.txt")
    if universe_id.startswith("portfolio_"):
        pid = int(universe_id.replace("portfolio_", ""))
        from models import PortfolioHolding
        rows = (
            db.query(Stock.ticker_yf)
            .join(PortfolioHolding, PortfolioHolding.stock_id == Stock.id)
            .filter(PortfolioHolding.portfolio_id == pid)
            .all()
        )
        return [r[0] for r in rows]
    if universe_id.startswith("sector:"):
        sector = universe_id.split(":", 1)[1]
        rows = db.query(Stock.ticker_yf).filter(Stock.sector == sector).limit(200).all()
        return [r[0] for r in rows]
    return []


def load_stock_features_df(db: Session, tickers: list[str]) -> pd.DataFrame:
    """Load stock + features as wide DataFrame indexed by ticker."""
    rows = (
        db.query(Stock, StockFeature, Exchange)
        .outerjoin(StockFeature, Stock.id == StockFeature.stock_id)
        .outerjoin(Exchange, Stock.exchange_id == Exchange.id)
        .filter(Stock.ticker_yf.in_(tickers))
        .all()
    )
    records = []
    for stock, feat, exch in rows:
        rec = {
            "ticker": stock.ticker_yf,
            "symbol": stock.symbol,
            "company_name": stock.company_name,
            "sector": stock.sector,
            "industry": stock.industry,
            "exchange": exch.code if exch else "",
            "currency": stock.currency,
            "market_cap": stock.market_cap,
        }
        if feat:
            for col in StockFeature.__table__.columns:
                if col.name not in ("id", "stock_id", "updated_at"):
                    rec[col.name] = getattr(feat, col.name)
        records.append(rec)
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records).set_index("ticker")
    return df


def load_ohlcv_wide(
    db: Session,
    tickers: list[str],
    period_days: int = 365,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (prices_wide, returns_wide) DataFrames."""
    cutoff = date.today() - timedelta(days=period_days)
    stock_map = {
        s.ticker_yf: s.id
        for s in db.query(Stock).filter(Stock.ticker_yf.in_(tickers)).all()
    }
    prices: dict[str, pd.Series] = {}
    for ticker, sid in stock_map.items():
        rows = (
            db.query(StockOHLCV)
            .filter(StockOHLCV.stock_id == sid, StockOHLCV.date >= cutoff)
            .order_by(StockOHLCV.date)
            .all()
        )
        if not rows:
            continue
        prices[ticker] = pd.Series(
            {r.date: r.close for r in rows},
            name=ticker,
        )
    if not prices:
        return pd.DataFrame(), pd.DataFrame()
    prices_df = pd.DataFrame(prices)
    prices_df.index = pd.to_datetime(prices_df.index)
    prices_df = prices_df.sort_index().ffill(limit=5)
    returns_df = prices_df.pct_change(fill_method=None).dropna(how="all")
    return prices_df, returns_df


def build_analytic_dataset(
    db: Session,
    tickers: list[str],
    period_days: int = 365,
    benchmark: str = "^GSPC",
) -> pd.DataFrame:
    """Merge DB features with calculated return-based features."""
    base = load_stock_features_df(db, tickers)
    if base.empty:
        return base

    prices_df, returns_df = load_ohlcv_wide(db, tickers, period_days)
    if not returns_df.empty and len(returns_df.columns) >= 2:
        calc = compute_features_for_universe(returns_df, prices_df)
        for col in calc.columns:
            if col not in base.columns or base[col].isna().all():
                base[col] = calc[col]
            else:
                base[col] = base[col].fillna(calc[col])

    # Week range percentages
    if "last_close" in base.columns:
        for w in (52, 100, 200):
            hi, lo = f"week_{w}_high", f"week_{w}_low"
            if hi in base.columns and lo in base.columns:
                denom = base[hi] - base[lo]
                base[f"week_{w}_pct"] = (
                    (base["last_close"] - base[lo]) / denom.replace(0, float("nan"))
                )

    return base
