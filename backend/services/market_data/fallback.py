"""
Secondary last-close when Yahoo/yfinance has no price.

Configure at least one of:
  - FINNHUB_API_KEY — https://finnhub.io/register (free tier)
  - STOOQ_API_KEY — from Stooq captcha flow (https://stooq.com/q/d/?s=...&get_apikey)

Order: Finnhub quote first, then Stooq daily CSV. Set MARKET_DATA_SECONDARY=none to disable.
"""

from __future__ import annotations

from typing import Optional, Tuple

from logger import get_logger

log = get_logger("market_data.fallback")

SecondaryResult = Tuple[Optional[float], str]


def secondary_last_close(ticker_yf: str) -> SecondaryResult:
    """Best effort last close from optional Finnhub and/or Stooq."""
    from config import FINNHUB_API_KEY, MARKET_DATA_SECONDARY, STOOQ_API_KEY
    from services.market_data.finnhub_client import fetch_last_close_from_finnhub
    from services.market_data.stooq_client import fetch_last_close_from_stooq

    mode = (MARKET_DATA_SECONDARY or "auto").strip().lower()
    if mode in ("none", "off", "false", "0", ""):
        return None, "disabled"

    t = (ticker_yf or "").strip()
    if not t:
        return None, "no_ticker"

    if FINNHUB_API_KEY:
        p = fetch_last_close_from_finnhub(t, FINNHUB_API_KEY)
        if p is not None:
            log.info("secondary last_close %s = %s (finnhub)", t, p)
            return p, "finnhub"

    if STOOQ_API_KEY:
        p = fetch_last_close_from_stooq(t, api_key=STOOQ_API_KEY)
        if p is not None:
            log.info("secondary last_close %s = %s (stooq)", t, p)
            return p, "stooq"

    if not FINNHUB_API_KEY and not STOOQ_API_KEY:
        log.debug("secondary skipped for %s: set FINNHUB_API_KEY and/or STOOQ_API_KEY", t)

    return None, "unavailable"
