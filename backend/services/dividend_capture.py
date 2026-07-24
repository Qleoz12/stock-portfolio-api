"""
Resolve the nearest future ex-date for a stock and compute dividend-capture Exp. APY.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Any, Optional, TypedDict

from sqlalchemy.orm import Session

from models import DividendForwardEvent, ManualCalendarDividend

_SOURCE_RANK = {"yahoo_ex": 0, "seasonal_1y": 1, "manual": 2}


class DividendCaptureSnapshot(TypedDict):
    next_ex_date: Optional[str]
    next_div_amount: Optional[float]
    days_to_next_ex: Optional[int]
    exp_div_apy_pct: Optional[float]
    next_div_source: Optional[str]


def _finite_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v):
        return None
    return v


def _source_rank(source: str) -> int:
    return _SOURCE_RANK.get(source, 99)


def _calendar_days_until(today: date, target: date) -> int:
    return (target - today).days


def _exp_div_apy_pct(div_amount: float, last_close: Optional[float], days: int) -> Optional[float]:
    price = _finite_float(last_close)
    amt = _finite_float(div_amount)
    if price is None or amt is None or price <= 0 or amt <= 0:
        return None
    denom = max(days, 1)
    apy = (amt / price) * (365.0 / denom) * 100.0
    return round(apy, 2) if math.isfinite(apy) else None


def _pick_best_candidate(
    candidates: list[tuple[date, float, str]],
) -> Optional[tuple[date, float, str]]:
    if not candidates:
        return None
    return min(candidates, key=lambda c: (c[0], _source_rank(c[2])))


def next_dividend_capture(
    db: Session,
    stock_id: int,
    last_close: Optional[float],
    *,
    as_of: Optional[date] = None,
) -> DividendCaptureSnapshot:
    """Nearest future ex-date from forward/manual calendar rows for composite outlook."""
    empty: DividendCaptureSnapshot = {
        "next_ex_date": None,
        "next_div_amount": None,
        "days_to_next_ex": None,
        "exp_div_apy_pct": None,
        "next_div_source": None,
    }
    today = as_of or date.today()
    candidates: list[tuple[date, float, str]] = []

    fwd_rows = (
        db.query(DividendForwardEvent)
        .filter(
            DividendForwardEvent.stock_id == stock_id,
            DividendForwardEvent.div_date >= today,
        )
        .order_by(DividendForwardEvent.div_date.asc())
        .all()
    )
    for row in fwd_rows:
        if row.div_date is None:
            continue
        src = (row.projection_source or "seasonal_1y").strip() or "seasonal_1y"
        candidates.append((row.div_date, _finite_amount(row.div_amount), src))

    manual_rows = (
        db.query(ManualCalendarDividend)
        .filter(
            ManualCalendarDividend.stock_id == stock_id,
            ManualCalendarDividend.div_date >= today,
        )
        .order_by(ManualCalendarDividend.div_date.asc())
        .all()
    )
    for row in manual_rows:
        if row.div_date is None:
            continue
        candidates.append((row.div_date, _finite_amount(row.div_amount), "manual"))

    best = _pick_best_candidate(candidates)
    if best is None:
        return empty

    ex_date, amount, source = best
    days = _calendar_days_until(today, ex_date)
    if days < 0:
        return empty

    return {
        "next_ex_date": str(ex_date),
        "next_div_amount": amount if amount > 0 else None,
        "days_to_next_ex": days,
        "exp_div_apy_pct": _exp_div_apy_pct(amount, last_close, days),
        "next_div_source": source,
    }


def _finite_amount(x: Any) -> float:
    v = _finite_float(x)
    return v if v is not None else 0.0
