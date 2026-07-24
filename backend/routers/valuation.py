"""Stock valuation — Model Value (GuruFocus-style, local yfinance model)."""

import os
import sys

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from database import get_db
from models import Stock, StockOHLCV
from routers.charts import _ensure_ohlcv_cache
from services.valuation_service import build_valuation_payload

router = APIRouter(prefix="/api/stocks", tags=["valuation"])


def _gurufocus_slug(ticker_yf: str) -> str:
    y = ticker_yf.strip().upper()
    dot = y.find(".")
    if dot > 0:
        root = y[:dot]
        suf = y[dot + 1 :]
        if suf in ("TO", "V"):
            return f"{root}:CA"
        if suf == "L":
            return f"{root}:LSE"
        if suf == "AX":
            return f"{root}:ASX"
        return root
    return y


@router.get("/{stock_id}/valuation")
def get_stock_valuation(
    stock_id: int,
    refresh: bool = Query(False),
    db: Session = Depends(get_db),
):
    stock = db.query(Stock).filter(Stock.id == stock_id).first()
    if not stock:
        raise HTTPException(status_code=404, detail="Stock not found")
    ticker = stock.ticker_yf or stock.symbol
    if not ticker:
        raise HTTPException(status_code=400, detail="Stock has no ticker")

    _ensure_ohlcv_cache(stock, db)
    rows = (
        db.query(StockOHLCV)
        .filter(StockOHLCV.stock_id == stock.id)
        .order_by(StockOHLCV.date.asc())
        .all()
    )
    dates = [r.date for r in rows]
    closes = [float(r.close) for r in rows if r.close is not None]

    gf_url = f"https://www.gurufocus.com/stock/{_gurufocus_slug(ticker)}/valuation"
    return build_valuation_payload(
        ticker_yf=ticker,
        company_name=stock.company_name or stock.symbol,
        gurufocus_url=gf_url,
        ohlcv_dates=dates,
        ohlcv_closes=closes,
        force_refresh=refresh,
    )
