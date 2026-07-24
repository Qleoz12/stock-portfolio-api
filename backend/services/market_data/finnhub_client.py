"""Finnhub quote (optional; requires FINNHUB_API_KEY)."""

from __future__ import annotations

from typing import Optional

import httpx

from logger import get_logger

log = get_logger("market_data.finnhub")

FINNHUB_QUOTE = "https://finnhub.io/api/v1/quote"


def fetch_last_close_from_finnhub(ticker_yf: str, api_key: str, timeout: float = 12.0) -> Optional[float]:
    """
    Current / last trade price from Finnhub quote endpoint.
    `c` is current price; falls back to `pc` (previous close) if needed.
    """
    if not api_key:
        return None
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(
                FINNHUB_QUOTE,
                params={"symbol": ticker_yf, "token": api_key},
            )
            r.raise_for_status()
        data = r.json()
        c = data.get("c")
        if c is not None and isinstance(c, (int, float)) and c > 0:
            return float(c)
        pc = data.get("pc")
        if pc is not None and isinstance(pc, (int, float)) and pc > 0:
            return float(pc)
    except Exception as e:
        log.debug("Finnhub quote failed for %s: %s", ticker_yf, e)
    return None
