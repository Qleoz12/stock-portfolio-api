"""Local Model Value (GuruFocus GF-style) from yfinance quarterly data + OHLCV."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

from logger import get_logger
from services.price_normalization import finite_float, ttm_from_quarterly

log = get_logger("valuation")

_CACHE: Dict[str, Any] = {}
_CACHE_TTL_SEC = 6 * 60 * 60

DISCLAIMER = (
    "Model Value is a local approximation based on historical median multiples (Yahoo Finance). "
    "It is not GuruFocus GF Value™."
)

_REVENUE_ROWS = ["Total Revenue", "TotalRevenue", "Revenue"]
_NI_ROWS = ["Net Income", "Net Income Common Stockholders", "NetIncome"]
_EPS_ROWS = ["Diluted EPS", "Basic EPS"]
_EQUITY_ROWS = [
    "Stockholders Equity",
    "Total Stockholder Equity",
    "Common Stock Equity",
    "Total Equity Gross Minority Interest",
]
_OCF_ROWS = ["Operating Cash Flow", "Total Cash From Operating Activities"]
_SHARES_ROWS = [
    "Ordinary Shares Number",
    "Share Issued",
    "Basic Average Shares",
    "Diluted Average Shares",
]


def verdict_from_ratio(ratio: Optional[float]) -> Tuple[str, str]:
    if ratio is None or not math.isfinite(ratio) or ratio <= 0:
        return "unknown", "Unknown"
    if ratio < 0.70:
        return "significantly_undervalued", "Significantly Undervalued"
    if ratio < 0.90:
        return "modestly_undervalued", "Modestly Undervalued"
    if ratio <= 1.10:
        return "fairly_valued", "Fairly Valued"
    if ratio <= 1.30:
        return "modestly_overvalued", "Modestly Overvalued"
    return "significantly_overvalued", "Significantly Overvalued"


def _row_series(df: Optional[pd.DataFrame], candidates: Sequence[str]) -> Optional[pd.Series]:
    if df is None or df.empty:
        return None
    name = next((n for n in candidates if n in df.index), None)
    if name is None:
        return None
    s = df.loc[name].copy()
    idx = pd.to_datetime(s.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_convert("UTC").tz_localize(None)
    s.index = idx
    return s.sort_index()


def _ttm_at_date(series: pd.Series, as_of: pd.Timestamp) -> Optional[float]:
    if series is None or series.empty:
        return None
    as_of = _normalize_ts(as_of)
    s = series[series.index <= as_of].dropna()
    if len(s) < 4:
        return None
    return finite_float(s.iloc[-4:].sum())


def _value_at_date(series: pd.Series, as_of: pd.Timestamp) -> Optional[float]:
    if series is None or series.empty:
        return None
    as_of = _normalize_ts(as_of)
    s = series[series.index <= as_of].dropna()
    if s.empty:
        return None
    return finite_float(s.iloc[-1])


def _median_positive(values: Sequence[Optional[float]]) -> Optional[float]:
    nums = [float(v) for v in values if v is not None and math.isfinite(v) and v > 0]
    if not nums:
        return None
    return float(np.median(nums))


def _pearson_pct(x: Sequence[float], y: Sequence[float]) -> Optional[float]:
    if len(x) < 4 or len(y) < 4 or len(x) != len(y):
        return None
    xa = np.array(x, dtype=float)
    ya = np.array(y, dtype=float)
    if np.std(xa) == 0 or np.std(ya) == 0:
        return None
    return round(float(np.corrcoef(xa, ya)[0, 1]) * 100, 0)


def _growth_rate(info: dict) -> Optional[float]:
    for key in ("earningsGrowth", "earningsQuarterlyGrowth", "revenueGrowth"):
        v = finite_float(info.get(key))
        if v is not None and math.isfinite(v):
            return v
    return None


def _build_narrative(company_name: str, price: float, model_value: float, verdict_label: str) -> str:
    name = company_name or "This company"
    ratio = price / model_value if model_value > 0 else None
    ratio_txt = f"{ratio:.2f}" if ratio is not None else "N/A"
    return (
        f"{name}'s share price is ${price:.2f}. Its Model Value is ${model_value:.2f}. "
        f"Based on the relationship between the current stock price and the Model Value "
        f"(Price/Model Value = {ratio_txt}), the stock appears {verdict_label}. "
        f"Compare with GuruFocus GF Value via the external link — numbers will differ."
    )


def _growth_rows(price: float, model_value: float, growth: Optional[float]) -> List[dict]:
    g = growth if growth is not None and math.isfinite(growth) else 0.05
    horizons = [
        ("current", "Current", 0.0),
        ("next_fy1", "Next FY1 End", 1.0),
        ("next_12m", "Next 12 Month", 1.0),
        ("next_fy2", "Next FY2 End", 2.0),
    ]
    rows: List[dict] = []
    for key, label, years in horizons:
        mv = model_value * ((1 + g) ** years)
        ratio = price / mv if mv > 0 else None
        rows.append(
            {
                "horizon": key,
                "label": label,
                "model_value": round(mv, 2),
                "ratio": round(ratio, 2) if ratio is not None else None,
            }
        )
    return rows


@dataclass
class QuarterMetrics:
    date: date
    price: float
    revenue_ps: Optional[float]
    book_ps: Optional[float]
    eps_ttm: Optional[float]
    ocf_ps_ttm: Optional[float]
    pe: Optional[float]
    ps: Optional[float]
    pb: Optional[float]
    pocf: Optional[float]


def _normalize_ts(ts: pd.Timestamp) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    if t.tzinfo is not None:
        return t.tz_convert("UTC").tz_localize(None)
    return t


def _normalize_price_index(prices: pd.Series) -> pd.Series:
    if prices is None or prices.empty:
        return prices
    idx = pd.to_datetime(prices.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_convert("UTC").tz_localize(None)
    out = prices.copy()
    out.index = idx
    return out.sort_index()


def _price_on_or_before(prices: pd.Series, ts: pd.Timestamp) -> Optional[float]:
    if prices is None or prices.empty:
        return None
    ts = _normalize_ts(ts)
    s = prices[prices.index <= ts]
    if s.empty:
        return None
    return finite_float(s.iloc[-1])


def build_quarter_metrics(
    qf: pd.DataFrame,
    qbs: pd.DataFrame,
    qcf: pd.DataFrame,
    prices: pd.Series,
    shares: Optional[float],
) -> List[QuarterMetrics]:
    rev = _row_series(qf, _REVENUE_ROWS)
    equity = _row_series(qbs, _EQUITY_ROWS)
    ocf = _row_series(qcf, _OCF_ROWS)
    eps = _row_series(qf, _EPS_ROWS)

    dates = sorted(set(d for d in [
        *(rev.index if rev is not None else []),
        *(equity.index if equity is not None else []),
        *(ocf.index if ocf is not None else []),
    ]))

    out: List[QuarterMetrics] = []
    sh = shares or 1.0
    if sh <= 0:
        sh = 1.0

    for ts in dates[-40:]:
        ts = _normalize_ts(pd.Timestamp(ts))
        if ts < _normalize_ts(pd.Timestamp.now()) - pd.DateOffset(years=10):
            continue
        price = _price_on_or_before(prices, ts)
        if price is None or price <= 0:
            continue

        rev_ttm = _ttm_at_date(rev, ts) if rev is not None else None
        ocf_ttm = _ttm_at_date(ocf, ts) if ocf is not None else None
        eps_ttm = _ttm_at_date(eps, ts) if eps is not None else None
        eq = _value_at_date(equity, ts) if equity is not None else None

        revenue_ps = (rev_ttm / sh) if rev_ttm and sh else None
        ocf_ps = (ocf_ttm / sh) if ocf_ttm and sh else None
        book_ps = (eq / sh) if eq and sh else None

        pe = price / eps_ttm if eps_ttm and eps_ttm > 0 else None
        ps = price / revenue_ps if revenue_ps and revenue_ps > 0 else None
        pb = price / book_ps if book_ps and book_ps > 0 else None
        pocf = price / ocf_ps if ocf_ps and ocf_ps > 0 else None

        out.append(
            QuarterMetrics(
                date=ts.date(),
                price=price,
                revenue_ps=finite_float(revenue_ps),
                book_ps=finite_float(book_ps),
                eps_ttm=finite_float(eps_ttm),
                ocf_ps_ttm=finite_float(ocf_ps),
                pe=finite_float(pe),
                ps=finite_float(ps),
                pb=finite_float(pb),
                pocf=finite_float(pocf),
            )
        )
    return out


def _model_value_from_medians(
    med_pe: Optional[float],
    med_ps: Optional[float],
    med_pb: Optional[float],
    med_pocf: Optional[float],
    eps_ttm: Optional[float],
    revenue_ps: Optional[float],
    book_ps: Optional[float],
    ocf_ps: Optional[float],
) -> Optional[float]:
    candidates: List[float] = []
    if med_pe and eps_ttm and eps_ttm > 0:
        candidates.append(med_pe * eps_ttm)
    if med_ps and revenue_ps and revenue_ps > 0:
        candidates.append(med_ps * revenue_ps)
    if med_pb and book_ps and book_ps > 0:
        candidates.append(med_pb * book_ps)
    if med_pocf and ocf_ps and ocf_ps > 0:
        candidates.append(med_pocf * ocf_ps)
    if len(candidates) < 2:
        if candidates:
            return candidates[0]
        return None
    return float(np.median(candidates))


def _correlation_block(
    metric_key: str,
    label: str,
    quarters: Sequence[QuarterMetrics],
    median_ratio: Optional[float],
    metric_attr: str,
    estimate_label: str,
) -> dict:
    dates: List[str] = []
    prices: List[float] = []
    metrics: List[float] = []
    implied: List[Optional[float]] = []

    for q in quarters:
        m = getattr(q, metric_attr, None)
        if m is None or m <= 0:
            continue
        dates.append(q.date.isoformat())
        prices.append(round(q.price, 2))
        metrics.append(round(m, 4))
        if median_ratio and median_ratio > 0:
            implied.append(round(median_ratio * m, 2))
        else:
            implied.append(None)

    corr = _pearson_pct(prices, metrics)
    latest_m = metrics[-1] if metrics else None
    price_at_median = (
        round(median_ratio * latest_m, 2)
        if median_ratio and latest_m and median_ratio > 0
        else None
    )

    return {
        "metric": metric_key,
        "label": label,
        "correlation_pct": corr,
        "price_at_median": price_at_median,
        "estimate_label": estimate_label,
        "chart": {
            "dates": dates,
            "price": prices,
            "metric_ps": metrics,
            "implied_price": implied,
        },
    }


def _value_series_weekly(
    prices: pd.Series,
    quarters: Sequence[QuarterMetrics],
    med_pe: Optional[float],
    med_ps: Optional[float],
    med_pb: Optional[float],
    med_pocf: Optional[float],
) -> dict:
    if prices is None or prices.empty:
        return {"dates": [], "price": [], "model_value": [], "bands": {}}

    weekly = prices.resample("W-FRI").last().dropna().tail(260)
    q_by_date = {q.date: q for q in quarters}

    dates: List[str] = []
    price_arr: List[float] = []
    mv_arr: List[Optional[float]] = []

    for ts, px in weekly.items():
        d = ts.date()
        q = q_by_date.get(d)
        if q is None:
            prior = [x for x in quarters if x.date <= d]
            q = prior[-1] if prior else None
        mv = None
        if q:
            mv = _model_value_from_medians(
                med_pe, med_ps, med_pb, med_pocf,
                q.eps_ttm, q.revenue_ps, q.book_ps, q.ocf_ps_ttm,
            )
        dates.append(d.isoformat())
        price_arr.append(round(float(px), 2))
        mv_arr.append(round(mv, 2) if mv else None)

    last_mv = next((v for v in reversed(mv_arr) if v is not None), None)
    if last_mv is None:
        last_mv = mv_arr[-1] if mv_arr else None

    def band(mult: float) -> List[Optional[float]]:
        return [round(v * mult, 2) if v else None for v in mv_arr]

    bands = {}
    if last_mv:
        for pct, key in [(1.1, "p10"), (1.2, "p20"), (1.3, "p30"), (0.9, "m10"), (0.8, "m20"), (0.7, "m30")]:
            bands[key] = band(pct)

    return {
        "dates": dates,
        "price": price_arr,
        "model_value": mv_arr,
        "bands": bands,
    }


def _historical_ratio_series(quarters: Sequence[QuarterMetrics], attr: str) -> dict:
    dates: List[str] = []
    values: List[float] = []
    for q in quarters:
        v = getattr(q, attr, None)
        if v is None or v <= 0 or v > 500:
            continue
        dates.append(q.date.isoformat())
        values.append(round(v, 2))
    recent = values[-20:] if len(values) >= 20 else values
    median_5y = round(float(np.median(recent)), 2) if recent else None
    return {"dates": dates, "values": values, "median_5y": median_5y}


def build_valuation_payload(
    ticker_yf: str,
    company_name: str,
    gurufocus_url: str,
    ohlcv_dates: Sequence[date],
    ohlcv_closes: Sequence[float],
    force_refresh: bool = False,
) -> dict:
    cache_key = ticker_yf
    now = time.time()
    if not force_refresh and cache_key in _CACHE and now < _CACHE[cache_key].get("expires_at", 0):
        return _CACHE[cache_key]["payload"]

    t = yf.Ticker(ticker_yf)
    info = t.info or {}

    qf = t.quarterly_financials
    qbs = t.quarterly_balance_sheet
    qcf = t.quarterly_cashflow

    if ohlcv_dates and ohlcv_closes:
        prices = _normalize_price_index(pd.Series(
            list(ohlcv_closes),
            index=pd.to_datetime(list(ohlcv_dates)),
        ))
    else:
        hist = t.history(period="10y", auto_adjust=False)
        prices = hist["Close"].dropna() if hist is not None and not hist.empty else pd.Series(dtype=float)

    prices = _normalize_price_index(prices)

    price = finite_float(info.get("currentPrice") or info.get("regularMarketPrice"))
    if price is None and not prices.empty:
        price = finite_float(prices.iloc[-1])
    if price is None:
        price = 0.0

    shares = finite_float(info.get("sharesOutstanding"))
    if shares is None and qbs is not None and not qbs.empty:
        sh_s = _row_series(qbs, _SHARES_ROWS)
        if sh_s is not None and not sh_s.empty:
            shares = finite_float(sh_s.iloc[0])

    quarters = build_quarter_metrics(qf, qbs, qcf, prices, shares)
    recent_20 = quarters[-20:] if len(quarters) >= 20 else quarters

    med_pe = _median_positive([q.pe for q in recent_20])
    med_ps = _median_positive([q.ps for q in recent_20])
    med_pb = _median_positive([q.pb for q in recent_20])
    med_pocf = _median_positive([q.pocf for q in recent_20])

    latest = quarters[-1] if quarters else None
    eps_ttm = latest.eps_ttm if latest else ttm_from_quarterly(qf, _EPS_ROWS)
    revenue_ps = latest.revenue_ps if latest else None
    book_ps = latest.book_ps if latest else None
    ocf_ps = latest.ocf_ps_ttm if latest else None

    if revenue_ps is None and qf is not None and shares:
        rev_ttm = ttm_from_quarterly(qf, _REVENUE_ROWS)
        if rev_ttm:
            revenue_ps = rev_ttm / shares
    if book_ps is None and qbs is not None and shares:
        eq_s = _row_series(qbs, _EQUITY_ROWS)
        if eq_s is not None and not eq_s.empty:
            book_ps = finite_float(eq_s.iloc[0] / shares)
    if ocf_ps is None and qcf is not None and shares:
        ocf_ttm = ttm_from_quarterly(qcf, _OCF_ROWS)
        if ocf_ttm:
            ocf_ps = ocf_ttm / shares

    model_value = _model_value_from_medians(
        med_pe, med_ps, med_pb, med_pocf,
        eps_ttm, revenue_ps, book_ps, ocf_ps,
    )

    ratio = price / model_value if model_value and model_value > 0 else None
    verdict, verdict_label = verdict_from_ratio(ratio)
    growth = _growth_rate(info)

    payload: dict = {
        "ticker": ticker_yf,
        "company_name": company_name,
        "price": round(price, 2),
        "model_value": round(model_value, 2) if model_value else None,
        "price_to_model_value": round(ratio, 2) if ratio else None,
        "verdict": verdict,
        "verdict_label": verdict_label,
        "narrative": (
            _build_narrative(company_name, price, model_value, verdict_label)
            if model_value
            else f"Insufficient quarterly data to compute Model Value for {ticker_yf}."
        ),
        "growth_rows": _growth_rows(price, model_value, growth) if model_value else [],
        "value_series": _value_series_weekly(prices, quarters, med_pe, med_ps, med_pb, med_pocf),
        "correlations": [
            _correlation_block("revenue", "Price vs Revenue", quarters, med_ps, "revenue_ps", "Med PS"),
            _correlation_block("book", "Price vs Book", quarters, med_pb, "book_ps", "Med PB"),
            _correlation_block("eps", "Price vs EPS without NRI", quarters, med_pe, "eps_ttm", "Med PE"),
            _correlation_block("ocf", "Price vs Operating Cash Flow", quarters, med_pocf, "ocf_ps_ttm", "Med P/OCF"),
        ],
        "historical_ratios": {
            "pe": _historical_ratio_series(quarters, "pe"),
            "ps": _historical_ratio_series(quarters, "ps"),
        },
        "gurufocus_url": gurufocus_url,
        "source": "yfinance+local_model",
        "disclaimer": DISCLAIMER,
        "data_quality": {
            "quarters_used": len(quarters),
            "has_model_value": model_value is not None,
            "growth_rate_used": growth,
        },
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }

    _CACHE[cache_key] = {"payload": payload, "expires_at": now + _CACHE_TTL_SEC}
    return payload
