"""
Polymarket Gamma API — read-only market discovery for prediction market comparison.
Docs: https://docs.polymarket.com (public, no API key).
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import POLYMARKET_GAMMA_BASE
from database import get_db
from logger import get_logger
from models import Stock
from services.strike_parser import parse_market_strike

log = get_logger("polymarket")

router = APIRouter(prefix="/api/polymarket", tags=["polymarket"])

_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_TTL_SEC = 300

_POLYMARKET_SITE = "https://polymarket.com"


def _cache_get(key: str) -> Any | None:
    entry = _CACHE.get(key)
    if not entry:
        return None
    ts, val = entry
    if time.time() - ts > _CACHE_TTL_SEC:
        _CACHE.pop(key, None)
        return None
    return val


def _cache_set(key: str, val: Any) -> None:
    _CACHE[key] = (time.time(), val)


def _gamma_get(path: str, params: dict[str, Any] | None = None) -> Any:
    url = f"{POLYMARKET_GAMMA_BASE}{path}"
    try:
        with httpx.Client(timeout=28.0) as client:
            r = client.get(url, params=params or {})
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        log.warning("Polymarket HTTP %s: %s", e.response.status_code, e.response.text[:200])
        raise HTTPException(
            status_code=502,
            detail="Polymarket Gamma API returned an error. Try again later.",
        ) from e
    except Exception as e:
        log.warning("Polymarket request failed: %s", e, exc_info=True)
        raise HTTPException(status_code=502, detail="Could not reach Polymarket Gamma API.") from e


def _parse_outcome_prices(raw: Any) -> tuple[Optional[float], Optional[float]]:
    if raw is None:
        return None, None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None, None
    if isinstance(raw, list) and len(raw) >= 2:
        try:
            yes = float(raw[0])
            no = float(raw[1])
            return yes, no
        except (TypeError, ValueError):
            return None, None
    return None, None


def _safe_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
        return f if f == f else None  # NaN check
    except (TypeError, ValueError):
        return None


def _market_url(slug: Optional[str], event_slug: Optional[str] = None) -> str:
    if slug:
        return f"{_POLYMARKET_SITE}/event/{slug}"
    if event_slug:
        return f"{_POLYMARKET_SITE}/event/{event_slug}"
    return _POLYMARKET_SITE


def normalize_polymarket_market(
    m: dict[str, Any],
    *,
    symbol_hint: Optional[str] = None,
    spot: Optional[float] = None,
    event_title: Optional[str] = None,
) -> dict[str, Any]:
    title = m.get("question") or m.get("title") or event_title or ""
    slug = m.get("slug") or m.get("market_slug")
    yes_p, no_p = _parse_outcome_prices(m.get("outcomePrices"))
    if yes_p is None:
        yes_p = _safe_float(m.get("lastTradePrice"))
    best_bid = _safe_float(m.get("bestBid"))
    best_ask = _safe_float(m.get("bestAsk"))
    yes_ask = best_ask if best_ask is not None else yes_p
    no_ask = (1.0 - best_bid) if best_bid is not None else no_p

    parsed = parse_market_strike(
        str(title),
        symbol_hint=symbol_hint,
        spot=spot,
        description=str(m.get("description") or ""),
    )

    vol = _safe_float(m.get("volume")) or _safe_float(m.get("volumeNum"))
    liq = _safe_float(m.get("liquidity")) or _safe_float(m.get("liquidityNum"))
    end = m.get("endDate") or m.get("end_date_iso") or m.get("expirationDate")

    return {
        "source": "polymarket",
        "title": title,
        "slug": slug,
        "url": _market_url(slug, m.get("event_slug")),
        "yes_implied_pct": round(yes_p * 100, 2) if yes_p is not None else None,
        "no_implied_pct": round(no_p * 100, 2) if no_p is not None else None,
        "yes_ask": round(yes_ask, 4) if yes_ask is not None else None,
        "no_ask": round(no_ask, 4) if no_ask is not None else None,
        "volume": vol,
        "liquidity": liq,
        "end_date": end,
        "strike_price": parsed.strike_price,
        "direction": parsed.direction,
        "period": parsed.period,
        "is_price_market": parsed.is_price_market,
        "resolution_note": parsed.resolution_note,
        "parsed_ticker": parsed.ticker,
    }


def _collect_markets_from_search(payload: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(m: dict[str, Any], event_title: str = "") -> None:
        key = str(m.get("id") or m.get("slug") or m.get("question") or "")
        if not key or key in seen:
            return
        seen.add(key)
        if event_title and not m.get("question"):
            m = {**m, "question": event_title}
        out.append(m)

    for m in payload.get("markets") or []:
        if isinstance(m, dict):
            add(m)
    for ev in payload.get("events") or []:
        if not isinstance(ev, dict):
            continue
        et = str(ev.get("title") or ev.get("name") or "")
        for m in ev.get("markets") or []:
            if isinstance(m, dict):
                add(m, et)
    return out


def polymarket_search_raw(query: str, *, limit: int = 24) -> list[dict[str, Any]]:
    cache_key = f"search:{query}:{limit}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    payload = _gamma_get(
        "/public-search",
        {"q": query, "limit_per_type": limit, "keep_closed_markets": 0},
    )
    if not isinstance(payload, dict):
        payload = {}
    raw = _collect_markets_from_search(payload)
    _cache_set(cache_key, raw)
    return raw


def polymarket_markets_for_stock(
    stock: Stock,
    *,
    limit: int = 20,
    spot: Optional[float] = None,
) -> list[dict[str, Any]]:
    sym = (stock.symbol or "").upper()
    name = (stock.company_name or "").strip()
    queries = [
        f"{sym} stock price",
        f"{name} {sym} price",
        f"{sym} reach",
    ]
    symbol_hint = sym
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []

    for q in queries:
        if len(normalized) >= limit:
            break
        try:
            raw = polymarket_search_raw(q, limit=limit)
        except HTTPException:
            continue
        for m in raw:
            key = str(m.get("slug") or m.get("question") or "")
            if not key or key in seen:
                continue
            blob = f"{m.get('question', '')} {m.get('title', '')}".upper()
            if sym and sym not in blob and sym not in (name or "").upper():
                # Keep if price market with strike (multi-stock events)
                row = normalize_polymarket_market(m, symbol_hint=symbol_hint, spot=spot)
                if not row.get("is_price_market"):
                    continue
            seen.add(key)
            normalized.append(
                normalize_polymarket_market(m, symbol_hint=symbol_hint, spot=spot)
            )
            if len(normalized) >= limit:
                break

    return normalized[:limit]


@router.get("/search")
def polymarket_search(
    q: str = Query(..., min_length=1),
    limit: int = Query(24, ge=4, le=48),
    price_only: bool = Query(False),
):
    """Hub: search Polymarket Gamma for finance / stock price markets."""
    cap = max(4, min(int(limit), 48))
    raw = polymarket_search_raw(q.strip(), limit=cap)
    markets = [normalize_polymarket_market(m) for m in raw[: cap * 2]]
    if price_only:
        markets = [m for m in markets if m.get("is_price_market")]
    markets = markets[:cap]
    return {
        "source": "polymarket",
        "query_used": q.strip(),
        "markets": markets,
        "total_candidates": len(raw),
        "shown": len(markets),
    }


@router.get("/stock/{stock_id}")
def polymarket_for_stock(stock_id: int, db: Session = Depends(get_db)):
    """Polymarket markets related to a stock ticker (any sector)."""
    stock = db.query(Stock).options(joinedload(Stock.features)).filter(Stock.id == stock_id).first()
    if not stock:
        raise HTTPException(status_code=404, detail="Stock not found")

    spot = None
    if stock.features and stock.features.last_close:
        spot = float(stock.features.last_close)

    markets = polymarket_markets_for_stock(stock, spot=spot)
    return {
        "enabled": True,
        "ticker": stock.symbol,
        "ticker_yf": stock.ticker_yf,
        "spot": spot,
        "markets": markets,
        "shown": len(markets),
    }
