"""
Parse Polymarket / prediction market titles for stock price strike levels.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# $90, $130.50, USD 90, 90 dollars
_PRICE_RE = re.compile(
    r"(?:\$|USD\s*)(\d{1,6}(?:\.\d{1,2})?)|(\d{1,6}(?:\.\d{1,2})?)\s*(?:dollars?|USD)",
    re.I,
)

# Ticker at start or after "Will"
_TICKER_RE = re.compile(r"\b([A-Z]{1,5}(?:\.[A-Z]{1,2})?)\b")

_ABOVE_RE = re.compile(
    r"(above|over|reach(?:es)?|hit(?:s)?|touch(?:es)?|at least|≥|>=|↑|⬆|high)",
    re.I,
)
_BELOW_RE = re.compile(
    r"(below|under|fall(?:s)? to|drop(?:s)? to|≤|<=|↓|⬇|low|or less)",
    re.I,
)

_PERIOD_RE = re.compile(
    r"(january|february|march|april|may|june|july|august|september|october|november|december)"
    r"[\s,]*(?:\d{4})?|"
    r"(?:Q[1-4]|quarter)\s*\d{4}|"
    r"\d{4}",
    re.I,
)

_STOCK_PRICE_HINTS = re.compile(
    r"(stock|share|price|close|trading|ticker|nasdaq|nyse|reach|touch|hit|fall|drop)",
    re.I,
)


@dataclass
class StrikeParseResult:
    ticker: Optional[str]
    strike_price: Optional[float]
    direction: Optional[str]  # touch_above | touch_below
    period: Optional[str]
    is_price_market: bool
    resolution_note: Optional[str]


def _first_price(text: str) -> Optional[float]:
    for m in _PRICE_RE.finditer(text):
        raw = m.group(1) or m.group(2)
        if raw:
            try:
                return float(raw)
            except ValueError:
                continue
    return None


def _guess_ticker(text: str, symbol_hint: Optional[str] = None) -> Optional[str]:
    if symbol_hint:
        return symbol_hint.upper().split(".")[0]
    upper = text.upper()
    # Common pattern: "Will HOOD reach..."
    m = re.search(r"\bWILL\s+([A-Z]{1,5})\b", upper)
    if m:
        return m.group(1)
    for m in _TICKER_RE.finditer(upper):
        tok = m.group(1)
        if tok not in frozenset({"USD", "NYSE", "NASDAQ", "WILL", "THE", "AND", "FOR", "YES", "NO"}):
            return tok.split(".")[0]
    return None


def _guess_direction(text: str, strike: Optional[float], spot: Optional[float] = None) -> Optional[str]:
    if _BELOW_RE.search(text):
        return "touch_below"
    if _ABOVE_RE.search(text):
        return "touch_above"
    if strike is not None and spot is not None:
        if strike < spot * 0.995:
            return "touch_below"
        if strike > spot * 1.005:
            return "touch_above"
    return None


def parse_market_strike(
    title: str,
    *,
    symbol_hint: Optional[str] = None,
    spot: Optional[float] = None,
    description: Optional[str] = None,
) -> StrikeParseResult:
    """Extract strike level and direction from a prediction market title."""
    blob = " ".join(filter(None, [title, description])).strip()
    if not blob:
        return StrikeParseResult(None, None, None, None, False, None)

    strike = _first_price(blob)
    ticker = _guess_ticker(blob, symbol_hint)
    direction = _guess_direction(blob, strike, spot)
    period_m = _PERIOD_RE.search(blob)
    period = period_m.group(0).strip() if period_m else None

    is_price = strike is not None and bool(_STOCK_PRICE_HINTS.search(blob) or symbol_hint)
    if strike is not None and ticker and not is_price:
        is_price = True

    note = None
    if is_price and strike is not None:
        note = (
            "Resolución típica: si el precio toca el nivel durante el periodo "
            "(sesión regular), no importa el cierre final."
        )

    return StrikeParseResult(
        ticker=ticker,
        strike_price=strike,
        direction=direction,
        period=period,
        is_price_market=is_price,
        resolution_note=note,
    )
