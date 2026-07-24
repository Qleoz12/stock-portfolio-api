"""
Simplified barrier-touch probability and bet EV helpers for prediction market comparison.
Not financial advice — educational approximation using log-normal / reflection principle.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional


TRADING_DAYS_PER_YEAR = 252


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def move_pct(spot: float, strike: float) -> Optional[float]:
    if not spot or spot <= 0:
        return None
    return round((strike - spot) / spot * 100.0, 2)


def period_volatility(annual_vol: float, trading_days: int) -> Optional[float]:
    if annual_vol is None or annual_vol <= 0 or trading_days <= 0:
        return None
    return annual_vol * math.sqrt(trading_days / TRADING_DAYS_PER_YEAR)


def z_score(spot: float, strike: float, sigma_period: float) -> Optional[float]:
    if not spot or not strike or not sigma_period or sigma_period <= 0:
        return None
    return math.log(strike / spot) / sigma_period


def touch_probability(
    spot: float,
    strike: float,
    annual_vol: float,
    trading_days: int,
    direction: Optional[str] = None,
) -> Optional[float]:
    """
    Approximate one-touch probability before expiry (zero-drift GBM reflection).
    Returns probability in [0, 1].
    """
    if spot <= 0 or strike <= 0 or annual_vol <= 0 or trading_days <= 0:
        return None

    sig_t = period_volatility(annual_vol, trading_days)
    if not sig_t:
        return None

    z = z_score(spot, strike, sig_t)
    if z is None:
        return None

    # Reflection principle: P(touch barrier) ≈ 2 * Φ(-|z|) for zero drift
    prob = 2.0 * norm_cdf(-abs(z))
    prob = max(0.0, min(1.0, prob))

    if direction == "touch_above" and strike < spot:
        return prob if strike < spot else None
    if direction == "touch_below" and strike > spot:
        return prob if strike < spot else None

    return round(prob, 4)


def trading_days_until(end: Optional[str | date | datetime]) -> Optional[int]:
    if end is None:
        return None
    if isinstance(end, datetime):
        end_d = end.date()
    elif isinstance(end, date):
        end_d = end
    else:
        s = str(end).strip()[:10]
        try:
            end_d = date.fromisoformat(s)
        except ValueError:
            return None
    today = date.today()
    delta = (end_d - today).days
    return max(1, int(delta * 5 / 7))  # approximate trading days from calendar days


@dataclass
class BetEvResult:
    price_paid: float
    stake: float
    gain_if_win: float
    loss_if_lose: float
    breakeven_prob: float
    ev_at_user_prob: Optional[float]
    edge_at_user_prob: Optional[float]


def bet_ev(
    price_paid: float,
    stake: float = 50.0,
    user_prob: Optional[float] = None,
    market_prob: Optional[float] = None,
) -> BetEvResult:
    """EV for buying Yes at price_paid (0–1) with fixed stake."""
    p = max(0.0, min(1.0, price_paid))
    stake = max(0.0, stake)
    contracts = stake / p if p > 0 else 0.0
    gain = contracts * (1.0 - p) if p < 1 else 0.0
    loss = stake

    breakeven = p
    ev = None
    edge = None
    if user_prob is not None:
        u = max(0.0, min(1.0, user_prob))
        ev = round(u * gain - (1.0 - u) * loss, 2)
        if market_prob is not None:
            edge = round(u - market_prob, 4)

    return BetEvResult(
        price_paid=round(p, 4),
        stake=stake,
        gain_if_win=round(gain, 2),
        loss_if_lose=round(loss, 2),
        breakeven_prob=round(breakeven, 4),
        ev_at_user_prob=ev,
        edge_at_user_prob=edge,
    )
