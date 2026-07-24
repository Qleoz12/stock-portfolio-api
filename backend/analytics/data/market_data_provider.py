"""Local-first market data access."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from models import Stock, StockOHLCV


class MarketDataProvider:
    """Read OHLCV from local DB; external refresh only when explicitly requested."""

    FRESHNESS_HOURS = {
        "prices": 24,
        "fundamentals": 168,
        "metadata": 720,
    }

    def __init__(self, db: Session) -> None:
        self.db = db
        self.external_requests = 0

    def find_prices(
        self,
        tickers: list[str],
        period_days: int = 365,
    ) -> dict[str, dict]:
        """Load OHLCV from local DB only."""
        cutoff = date.today() - timedelta(days=period_days)
        stock_map = {
            s.ticker_yf: s.id
            for s in self.db.query(Stock).filter(Stock.ticker_yf.in_(tickers)).all()
        }
        result: dict[str, dict] = {}
        for ticker, sid in stock_map.items():
            rows = (
                self.db.query(StockOHLCV)
                .filter(StockOHLCV.stock_id == sid, StockOHLCV.date >= cutoff)
                .order_by(StockOHLCV.date)
                .all()
            )
            if rows:
                result[ticker] = {
                    "dates": [r.date.isoformat() for r in rows],
                    "closes": [r.close for r in rows],
                    "source": "local_database",
                    "count": len(rows),
                }
        return result

    def get_freshness(self, ticker: str) -> dict:
        stock = self.db.query(Stock).filter(Stock.ticker_yf == ticker).first()
        if not stock:
            return {"status": "missing", "ticker": ticker}
        last = (
            self.db.query(StockOHLCV.date)
            .filter(StockOHLCV.stock_id == stock.id)
            .order_by(StockOHLCV.date.desc())
            .first()
        )
        if not last:
            return {"status": "no_ohlcv", "ticker": ticker}
        age_days = (date.today() - last[0]).days
        return {
            "ticker": ticker,
            "last_date": last[0].isoformat(),
            "age_days": age_days,
            "status": "current" if age_days <= 2 else "stale",
        }

    def refresh_missing(self, tickers: list[str]) -> dict:
        """Placeholder — triggers repair script logic; counts as external only when implemented."""
        missing = []
        for t in tickers:
            f = self.get_freshness(t)
            if f.get("status") in ("missing", "no_ohlcv"):
                missing.append(t)
        return {
            "requested": len(missing),
            "missing_tickers": missing,
            "external_requests": 0,
            "message": "Use scripts/add_stocks.py and repair_ohlcv_table.py to refresh missing data",
        }
