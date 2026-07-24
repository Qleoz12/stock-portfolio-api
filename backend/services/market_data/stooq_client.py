"""Daily EOD CSV from Stooq (no API key)."""

from __future__ import annotations

import csv
import io
from typing import Optional

import httpx

from logger import get_logger
from services.market_data.ticker_symbols import yahoo_to_stooq_symbol

log = get_logger("market_data.stooq")

STOOQ_DAILY_URL = "https://stooq.com/q/d/l/"


def fetch_last_close_from_stooq(
    ticker_yf: str,
    api_key: Optional[str] = None,
    timeout: float = 15.0,
) -> Optional[float]:
    """
    Last row Close from Stooq daily CSV. Stooq often requires `apikey` for automated
    downloads (see https://stooq.com/q/d/?s=...&get_apikey). Without a key the
    server may return instructions instead of CSV.
    """
    sym = yahoo_to_stooq_symbol(ticker_yf)
    params: dict = {"s": sym, "i": "d"}
    if api_key:
        params["apikey"] = api_key
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(STOOQ_DAILY_URL, params=params)
            r.raise_for_status()
        text = (r.text or "").strip()
        if not text or "No data" in text.lower():
            return None
        if "get your apikey" in text.lower():
            log.debug("Stooq requires apikey for %s (set STOOQ_API_KEY)", ticker_yf)
            return None
        lines = text.splitlines()
        if len(lines) < 2:
            return None
        reader = csv.reader(io.StringIO(text))
        header = next(reader, None)
        if not header:
            return None
        try:
            close_idx = [h.strip().lower() for h in header].index("close")
        except ValueError:
            close_idx = 4 if len(header) > 4 else -1
        if close_idx < 0:
            return None
        last_row = None
        for row in reader:
            if row and len(row) > close_idx:
                last_row = row
        if not last_row:
            return None
        v = float(last_row[close_idx].strip())
        if not (v == v):  # NaN
            return None
        return v
    except Exception as e:
        log.debug("Stooq last_close failed for %s (%s): %s", ticker_yf, sym, e)
        return None
