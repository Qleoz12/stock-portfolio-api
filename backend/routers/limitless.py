"""
Limitless Exchange (prediction markets) — read-only market search for analyst context.
Docs: https://api.limitless.exchange (X-API-Key optional; improves rate limits when set).
"""
import os
import re
import sys
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import LIMITLESS_API_BASE, LIMITLESS_API_KEY
from database import get_db
from logger import get_logger
from models import Stock

log = get_logger("limitless")

router = APIRouter(prefix="/api/limitless", tags=["limitless"])

# GICS + common TSX/LSE style labels treated as "banking / financial" for UI gate.
# Broad enough for GICS + TSX/LSE labels + Spanish fragments ("Financiero", "Banca").
_BANKING_SECTOR_RE = re.compile(
    r"(financial|financ|bank|banca|banking|insurance|capital market|credit|mortgage|"
    r"asset management|wealth|lending|fintech|broker|payments)",
    re.I,
)


def _is_banking_sector(sector: Optional[str]) -> bool:
    if not sector or not str(sector).strip():
        return False
    return bool(_BANKING_SECTOR_RE.search(sector))


def _is_macro_benchmark_ticker(stock: Stock) -> bool:
    """Broad indices / macro ETFs — useful for Fed/rates/macro prediction markets (e.g. KS11, SPY)."""
    ty = (stock.ticker_yf or "").upper()
    sym = (stock.symbol or "").upper()
    name = (stock.company_name or "").upper()
    base = ty.split(".")[0].replace("^", "")
    if base in frozenset(
        {"KS11", "EWY", "SPY", "QQQ", "DIA", "IWM", "VTI", "VOO", "IVV", "GSPC", "IXIC", "DJI", "VIX"}
    ):
        return True
    if any(h in ty for h in ("^GSPC", "^IXIC", "^DJI", "^VIX", "^KS11")):
        return True
    if "KOSPI" in name or "KOSPI" in sym:
        return True
    return False


def _limitless_allowed(stock: Stock) -> bool:
    return _is_banking_sector(stock.sector) or _is_macro_benchmark_ticker(stock)


_FIN_MARKET_TERMS = (
    "bank",
    "fed",
    "federal reserve",
    "treasury",
    "interest rate",
    "rate hike",
    "eps",
    "earnings",
    "financial",
    "loan",
    "mortgage",
    "credit",
    "gdp",
    "inflation",
    "recession",
    "dividend",
    "yield curve",
)


def _market_finance_relevant(m: dict) -> bool:
    blob = " ".join(
        [
            str(m.get("title") or ""),
            str(m.get("proxyTitle") or ""),
            " ".join(m.get("categories") or []),
            " ".join(m.get("tags") or []),
        ]
    ).lower()
    return any(t in blob for t in _FIN_MARKET_TERMS)


def _normalize_market(m: dict[str, Any]) -> dict[str, Any]:
    prices = m.get("prices") or []
    yes = prices[0] if len(prices) > 0 else None
    no = prices[1] if len(prices) > 1 else None
    return {
        "title": m.get("title"),
        "slug": m.get("slug"),
        "yes_implied_pct": round(float(yes) * 100, 2) if yes is not None else None,
        "no_implied_pct": round(float(no) * 100, 2) if no is not None else None,
        "volume_formatted": m.get("volumeFormatted"),
        "expiration_date": m.get("expirationDate"),
        "trade_type": m.get("tradeType"),
        "categories": m.get("categories") or [],
        "tags": (m.get("tags") or [])[:12],
    }


_FINANCE_HUB_BASE_QUERY = (
    "Federal Reserve interest rates inflation GDP recession earnings banks "
    "stocks treasury mortgage credit dividend yield curve financial markets SP500 NASDAQ"
)


def _limitless_search_raw(
    query: str,
    *,
    limit: int = 18,
    page: int = 1,
    similarity_threshold: float = 0.35,
) -> list[dict[str, Any]]:
    headers: dict[str, str] = {}
    if LIMITLESS_API_KEY:
        headers["X-API-Key"] = LIMITLESS_API_KEY
    url = f"{LIMITLESS_API_BASE}/markets/search"
    params = {
        "query": query,
        "limit": limit,
        "page": page,
        "similarityThreshold": similarity_threshold,
    }
    try:
        with httpx.Client(timeout=28.0) as client:
            r = client.get(url, params=params, headers=headers)
            r.raise_for_status()
            payload = r.json()
    except httpx.HTTPStatusError as e:
        log.warning("Limitless HTTP error: %s %s", e.response.status_code, e.response.text[:200])
        raise HTTPException(
            status_code=502,
            detail="Limitless API returned an error. Check API key or try later.",
        ) from e
    except Exception as e:
        log.warning("Limitless request failed: %s", e, exc_info=True)
        raise HTTPException(status_code=502, detail="Could not reach Limitless API.") from e
    raw = payload.get("markets") or payload.get("data") or []
    if not isinstance(raw, list):
        return []
    return [m for m in raw if isinstance(m, dict)]


@router.get("/finance-markets")
def limitless_finance_markets(q: Optional[str] = None, limit: int = 24):
    """
    Hub page: semantic search on Limitless restricted to finance-themed markets (same filter as per-stock).
    Optional `q` narrows the search; Polymarket and other sources can be added later as separate tabs.
    """
    base = _FINANCE_HUB_BASE_QUERY
    if q and str(q).strip():
        query = f"{str(q).strip()} {base}"
    else:
        query = base
    cap = max(8, min(int(limit), 48))
    raw = _limitless_search_raw(query, limit=cap, page=1)
    filtered = [m for m in raw if _market_finance_relevant(m)]
    pick = filtered[:cap] if filtered else raw[:cap]
    markets = [_normalize_market(m) for m in pick]
    return {
        "source": "limitless",
        "query_used": query,
        "markets": markets,
        "total_candidates": len(raw),
        "shown": len(markets),
        "api_key_used": bool(LIMITLESS_API_KEY),
    }


@router.get("/stock/{stock_id}")
def limitless_intel_for_stock(stock_id: int, db: Session = Depends(get_db)):
    """
    Semantic search on Limitless for finance-themed markets related to this ticker.
    Enabled for banking / financial sectors or major index / macro benchmarks (e.g. KS11, SPY).
    """
    stock = db.query(Stock).filter(Stock.id == stock_id).first()
    if not stock:
        raise HTTPException(status_code=404, detail="Stock not found")

    sector = stock.sector or ""
    if not _limitless_allowed(stock):
        return {
            "enabled": False,
            "sector": sector,
            "reason": (
                "Limitless odds are shown for banking / financial-sector names "
                "or major index / macro benchmarks (e.g. KS11, SPY, ^GSPC)."
            ),
        }

    if _is_banking_sector(sector):
        query = (
            f"{stock.company_name} {stock.symbol} banking banks Federal Reserve "
            f"interest rates earnings EPS financial stocks"
        )
    else:
        query = (
            f"{stock.company_name} {stock.symbol} Federal Reserve interest rates inflation "
            f"GDP recession Korea Asia stocks macro"
        )

    raw = _limitless_search_raw(query, limit=18, page=1)

    filtered = [m for m in raw if _market_finance_relevant(m)]
    pick = filtered[:8] if filtered else raw[:8]

    markets = [_normalize_market(m) for m in pick]

    return {
        "enabled": True,
        "sector": sector,
        "query_used": query,
        "markets": markets,
        "total_candidates": len(raw),
        "shown": len(markets),
        "api_key_used": bool(LIMITLESS_API_KEY),
    }
