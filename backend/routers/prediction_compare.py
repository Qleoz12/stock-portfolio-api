"""
Unified prediction market comparison: Polymarket odds vs local fundamentals / vol model.
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from database import get_db
from logger import get_logger
from models import Stock
from routers.charts import _ensure_ohlcv_cache
from routers.polymarket import polymarket_markets_for_stock
from routers.stocks import _build_price_normalization
from routers.valuation import _gurufocus_slug
from services.touch_probability import (
    bet_ev,
    move_pct,
    touch_probability,
    trading_days_until,
)
from services.valuation_service import build_valuation_payload

log = get_logger("prediction_compare")

router = APIRouter(prefix="/api/stocks", tags=["prediction"])


def _coerce_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()[:10]
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _week_52_pct(low: Optional[float], high: Optional[float], close: Optional[float]) -> Optional[float]:
    if not low or not high or not close or high <= low:
        return None
    return round((close - low) / (high - low) * 100.0, 2)


def _enrich_market_row(
    m: dict[str, Any],
    *,
    spot: Optional[float],
    annual_vol: Optional[float],
    user_prob: Optional[float],
    stake: float,
    earnings_date: Optional[date],
) -> dict[str, Any]:
    strike = m.get("strike_price")
    direction = m.get("direction")
    end = m.get("end_date")
    days = trading_days_until(end)

    move = move_pct(spot, strike) if spot and strike else None
    model_touch = None
    if spot and strike and annual_vol and days:
        model_touch = touch_probability(spot, strike, annual_vol, days, direction)

    yes_ask = m.get("yes_ask")
    if yes_ask is None and m.get("yes_implied_pct") is not None:
        yes_ask = m["yes_implied_pct"] / 100.0

    market_prob = yes_ask
    ev_yes = bet_ev(yes_ask or 0.5, stake=stake, user_prob=user_prob, market_prob=market_prob)

    earnings_risk = False
    if earnings_date and end:
        end_d = _coerce_date(end)
        if end_d and earnings_date <= end_d:
            earnings_risk = True

    return {
        **m,
        "move_pct": move,
        "trading_days_left": days,
        "model_touch_prob": model_touch,
        "model_touch_pct": round(model_touch * 100, 2) if model_touch is not None else None,
        "breakeven_prob_pct": round(ev_yes.breakeven_prob * 100, 2),
        "ev_stake": stake,
        "ev_gain_if_win": ev_yes.gain_if_win,
        "ev_loss_if_lose": ev_yes.loss_if_lose,
        "ev_at_user_prob": ev_yes.ev_at_user_prob,
        "edge_at_user_prob": ev_yes.edge_at_user_prob,
        "earnings_risk": earnings_risk,
    }


@router.get("/{stock_id}/prediction-compare")
def prediction_compare(
    stock_id: int,
    user_prob: Optional[float] = Query(None, ge=0, le=1, description="Your probability for Yes on primary strike"),
    stake: float = Query(50.0, ge=1, le=10000),
    db: Session = Depends(get_db),
):
    stock = db.query(Stock).options(joinedload(Stock.features)).filter(Stock.id == stock_id).first()
    if not stock:
        raise HTTPException(status_code=404, detail="Stock not found")

    feat = stock.features
    spot = float(feat.last_close) if feat and feat.last_close else None
    w52_low = float(feat.week_52_low) if feat and feat.week_52_low else None
    w52_high = float(feat.week_52_high) if feat and feat.week_52_high else None
    w52_pct = _week_52_pct(w52_low, w52_high, spot)

    earnings_date = _coerce_date(feat.next_earnings_date) if feat and feat.next_earnings_date else None

    annual_vol = None
    beta = None
    try:
        norm = _build_price_normalization(stock_id, db)
        annual_vol = norm.volatility_1y
        beta = norm.beta
        if spot is None and norm.price:
            spot = norm.price
    except HTTPException:
        pass

    model_value = None
    price_to_model = None
    ticker = stock.ticker_yf or stock.symbol
    gf_url = f"https://www.gurufocus.com/stock/{_gurufocus_slug(ticker)}/valuation"
    try:
        _ensure_ohlcv_cache(stock, db)
        from models import StockOHLCV

        rows = (
            db.query(StockOHLCV)
            .filter(StockOHLCV.stock_id == stock.id)
            .order_by(StockOHLCV.date.asc())
            .all()
        )
        dates = [r.date for r in rows]
        closes = [float(r.close) for r in rows if r.close is not None]
        val = build_valuation_payload(
            ticker_yf=ticker,
            company_name=stock.company_name or stock.symbol,
            gurufocus_url=gf_url,
            ohlcv_dates=dates,
            ohlcv_closes=closes,
            force_refresh=False,
        )
        model_value = val.get("model_value")
        price_to_model = val.get("price_to_model_value")
    except Exception as e:
        log.warning("valuation for prediction-compare failed: %s", e)

    raw_markets = polymarket_markets_for_stock(stock, spot=spot, limit=24)
    price_markets = [m for m in raw_markets if m.get("is_price_market") and m.get("strike_price")]
    markets = [
        _enrich_market_row(
            m,
            spot=spot,
            annual_vol=annual_vol,
            user_prob=user_prob,
            stake=stake,
            earnings_date=earnings_date,
        )
        for m in (price_markets or raw_markets)
    ]

    # Sort price markets by strike
    markets.sort(key=lambda x: (x.get("strike_price") is None, x.get("strike_price") or 0))

    primary = markets[0] if markets else None
    primary_days = primary.get("trading_days_left") if primary else None

    return {
        "ticker": stock.symbol,
        "ticker_yf": stock.ticker_yf,
        "company_name": stock.company_name,
        "spot": spot,
        "model_value": model_value,
        "price_to_model_value": price_to_model,
        "week_52_low": w52_low,
        "week_52_high": w52_high,
        "week_52_pct": w52_pct,
        "volatility_1y": annual_vol,
        "volatility_1y_pct": round(annual_vol * 100, 2) if annual_vol else None,
        "beta": beta,
        "next_earnings_date": earnings_date.isoformat() if earnings_date else None,
        "gurufocus_url": gf_url,
        "stake_example": stake,
        "user_prob": user_prob,
        "primary_market_days_left": primary_days,
        "markets": markets,
        "disclaimer": (
            "Probabilidades de modelo son aproximaciones educativas (volatilidad histórica). "
            "Polymarket pregunta si el precio TOCA el nivel durante el periodo, no dónde cierra. "
            "No es asesoría financiera."
        ),
    }
