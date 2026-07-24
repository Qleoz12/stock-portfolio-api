"""Per-stock Yahoo news sentiment (7-day daily buckets)."""

import os
import sys

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from database import get_db
from models import Stock
from services.news_sentiment_service import build_stock_news_sentiment

router = APIRouter(prefix="/api/news-sentiment", tags=["news-sentiment"])


@router.get("/stock/{stock_id}")
def get_stock_news_sentiment(
    stock_id: int,
    days: int = Query(7, ge=1, le=14),
    refresh: bool = Query(False),
    db: Session = Depends(get_db),
):
    stock = db.query(Stock).filter(Stock.id == stock_id).first()
    if not stock:
        raise HTTPException(status_code=404, detail="Stock not found")
    ticker = stock.ticker_yf or stock.symbol
    if not ticker:
        raise HTTPException(status_code=400, detail="Stock has no ticker")
    return build_stock_news_sentiment(ticker, days=days, force_refresh=refresh)
