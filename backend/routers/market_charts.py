"""
Proxy Yahoo Finance chart v8 para la vista Sectors (mini series diarias).
"""
from __future__ import annotations

import asyncio
import sys
import os
from datetime import datetime, timezone
from typing import Any, Literal

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from logger import get_logger

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models import Stock as DbStock, Exchange as DbExchange

log = get_logger("routers.market_charts")

router = APIRouter(prefix="/api/market", tags=["market"])

ExchangeParam = Literal["NASDAQ", "NYSE", "BVC", "Korea"]

_YAHOO_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_SECTOR_UNIVERSE: dict[ExchangeParam, list[tuple[str, str]]] = {
    "NYSE": [
        ("XLB", "Materiales"),
        ("XLY", "Consumo discrecional"),
        ("XLP", "Consumo básico"),
        ("XLE", "Energía"),
        ("XLF", "Financiero"),
        ("XLV", "Sanidad"),
        ("XLI", "Industrial"),
        ("XLK", "Tecnología"),
        ("XLC", "Comunicaciones"),
        ("XLU", "Utilities"),
        ("XLRE", "Inmobiliario"),
        ("SPY", "S&P 500"),
    ],
    "NASDAQ": [
        ("QQQ", "Nasdaq 100"),
        ("SOXX", "Semiconductores"),
        ("SMH", "Semis (VanEck)"),
        ("IGV", "Software"),
        ("IBB", "Biotech"),
        ("XLK", "Tecnología (SPDR)"),
        ("XLC", "Comunicaciones"),
        ("FDN", "Internet / cloud"),
        ("QTEC", "Nasdaq-100 Tech"),
        ("XLY", "Consumo discrecional"),
        ("XLF", "Financiero"),
        ("XLE", "Energía"),
    ],
    "Korea": [
        ("069500.KS", "KOSPI 200 (KODEX)"),
        ("229200.KS", "KOSPI (KODEX)"),
        ("102780.KS", "Semiconductores"),
        ("091160.KS", "Bancos"),
        ("EWY", "MSCI Korea (ETF EE.UU.)"),
    ],
    "BVC": [
        ("ICOL", "MSCI Colombia / proxy índice (ETF, USD)"),
        ("ECOPETL.BO", "Ecopetrol (BVC, COP)"),
        ("PFBCOLOM.BO", "Bancolombia pref. (BVC)"),
        ("BCOLOMBIA.BO", "Bancolombia ord. (BVC)"),
        ("ISA.BO", "ISA (utilities / energía)"),
        ("GEB.BO", "Grupo Energía Bogotá"),
        ("CEMARGOS.BO", "Cementos Argos"),
        ("GRUPOARGOS.BO", "Grupo Argos"),
        ("BOGOTA.BO", "Banco de Bogotá"),
        ("PFDAVVNDA.BO", "Davivienda pref."),
        ("NUTRESA.BO", "Grupo Nutresa"),
        ("CIB", "Bancolombia (ADR, USD)"),
        ("EC", "Ecopetrol (ADR, USD)"),
        ("AVAL", "Grupo Aval (ADR, USD)"),
    ],
}


class SectorChartItem(BaseModel):
    yahoo: str
    sector: str
    closes: list[float | None] = Field(default_factory=list)
    times: list[int] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)
    """[open, close, low, high] por barra (formato ECharts candlestick)."""
    ohlc: list[list[float]] = Field(default_factory=list)
    volumes: list[float] = Field(default_factory=list)
    last: float | None = None
    change_pct: float | None = None
    currency: str | None = None
    error: str | None = None
    stock_id: int | None = None


class SectorChartsMacro(BaseModel):
    """Snapshot FX / macro cuando aplica (p. ej. Colombia)."""

    usd_cop_last: float | None = None
    usd_cop_change_pct: float | None = None


class SectorChartsCoverage(BaseModel):
    ok: int
    total: int


class SectorChartsResponse(BaseModel):
    exchange: str
    as_of: str
    source: str = "yahoo_chart_v8"
    items: list[SectorChartItem]
    macro: SectorChartsMacro | None = None
    coverage: SectorChartsCoverage | None = None


class SectorEquityChartsResponse(BaseModel):
    """Paginated mini-charts for all DB tickers in a sector (optional exchange filter)."""

    sector: str
    exchange_filter: str | None = None
    page: int
    page_size: int
    total: int
    pages: int
    as_of: str
    source: str = "yahoo_chart_v8"
    items: list[SectorChartItem]
    coverage: SectorChartsCoverage | None = None


def _extract_rows(
    payload: dict[str, Any],
    max_bars: int = 72,
) -> tuple[list[tuple[int, str, float, float, float, float, float]], float | None, float | None, str | None]:
    """
    Devuelve filas (ts, date_utc, open, close, low, high, volume), last, change_pct, currency.
    OHLC alineado a Yahoo quote; velas ECharts usan [open, close, low, high].
    """
    chart = payload.get("chart") or {}
    err = chart.get("error")
    if err:
        desc = err.get("description") if isinstance(err, dict) else str(err)
        raise ValueError(desc or "chart error")
    results = chart.get("result")
    if not results:
        raise ValueError("sin resultados")
    r0 = results[0]
    meta = r0.get("meta") or {}
    ts_list = r0.get("timestamp") or []
    quote = (r0.get("indicators") or {}).get("quote") or [{}]
    q0 = quote[0] if quote else {}
    opens = q0.get("open") or []
    highs = q0.get("high") or []
    lows = q0.get("low") or []
    closes = q0.get("close") or []
    vols = q0.get("volume") or []
    n = min(len(ts_list), len(closes))
    rows: list[tuple[int, str, float, float, float, float, float]] = []
    for i in range(n):
        c_raw = closes[i]
        if c_raw is None:
            continue
        c = float(c_raw)
        t = int(ts_list[i])
        o_raw = opens[i] if i < len(opens) else None
        o = float(o_raw) if o_raw is not None else c
        h_raw = highs[i] if i < len(highs) else None
        l_raw = lows[i] if i < len(lows) else None
        h = float(h_raw) if h_raw is not None else max(o, c)
        l = float(l_raw) if l_raw is not None else min(o, c)
        h = max(h, o, c)
        l = min(l, o, c)
        v_raw = vols[i] if i < len(vols) else None
        v = float(v_raw) if v_raw is not None else 0.0
        d_str = datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d")
        rows.append((t, d_str, o, c, l, h, v))
    rows = rows[-max_bars:]
    last = meta.get("regularMarketPrice")
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    change_pct = None
    if last is not None and prev not in (None, 0):
        try:
            change_pct = round((float(last) - float(prev)) / float(prev) * 100.0, 2)
        except (TypeError, ValueError):
            change_pct = None
    currency = meta.get("currency")
    return rows, float(last) if last is not None else None, change_pct, currency


async def _fetch_one(
    client: httpx.AsyncClient,
    yahoo: str,
    sector: str,
    stock_id: int | None = None,
) -> SectorChartItem:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo}"
    params = {"interval": "1d", "range": "3mo"}
    try:
        r = await client.get(
            url,
            params=params,
            headers={"User-Agent": _YAHOO_UA, "Accept": "application/json"},
            timeout=20.0,
        )
        r.raise_for_status()
        data = r.json()
        rows, last, change_pct, currency = _extract_rows(data)
        if not rows:
            return SectorChartItem(yahoo=yahoo, sector=sector, error="sin precios de cierre", stock_id=stock_id)
        times = [x[0] for x in rows]
        dates = [x[1] for x in rows]
        closes_only = [x[3] for x in rows]
        ohlc = [[x[2], x[3], x[4], x[5]] for x in rows]
        volumes = [x[6] for x in rows]
        return SectorChartItem(
            yahoo=yahoo,
            sector=sector,
            closes=closes_only,
            times=times,
            dates=dates,
            ohlc=ohlc,
            volumes=volumes,
            last=last,
            change_pct=change_pct,
            currency=currency,
            stock_id=stock_id,
        )
    except Exception as e:
        log.warning("Yahoo chart falló %s: %s", yahoo, e)
        return SectorChartItem(yahoo=yahoo, sector=sector, error=str(e)[:200], stock_id=stock_id)


@router.get("/sector-charts", response_model=SectorChartsResponse)
async def sector_charts(
    exchange: ExchangeParam = Query("NYSE", description="NASDAQ | NYSE | BVC | Korea"),
):
    pairs = _SECTOR_UNIVERSE.get(exchange)
    if not pairs:
        raise HTTPException(400, "exchange inválido")
    as_of = datetime.now(timezone.utc).isoformat()
    async with httpx.AsyncClient() as client:
        tasks = [_fetch_one(client, y, label) for y, label in pairs]
        items = await asyncio.gather(*tasks)
        item_list = list(items)
        macro: SectorChartsMacro | None = None
        if exchange == "BVC":
            fx = await _fetch_one(client, "USDCOP=X", "USD/COP")
            macro = SectorChartsMacro(
                usd_cop_last=fx.last,
                usd_cop_change_pct=fx.change_pct,
            )
    ok_n = sum(1 for it in item_list if not it.error)
    coverage = SectorChartsCoverage(ok=ok_n, total=len(item_list))
    return SectorChartsResponse(
        exchange=exchange,
        as_of=as_of,
        items=item_list,
        macro=macro,
        coverage=coverage,
    )


@router.get("/sector-equity-charts", response_model=SectorEquityChartsResponse)
async def sector_equity_charts(
    sector: str = Query(..., min_length=1, description="Exact sector label from the database"),
    exchange: str | None = Query(None, description="Optional exchange code, e.g. NYSE"),
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=48),
    db: Session = Depends(get_db),
):
    sec = sector.strip()
    if not sec:
        raise HTTPException(400, "sector required")
    base = (
        db.query(DbStock.id, DbStock.ticker_yf, DbStock.company_name)
        .outerjoin(DbExchange, DbStock.exchange_id == DbExchange.id)
        .filter(DbStock.sector == sec)
    )
    if exchange and exchange.strip():
        base = base.filter(DbExchange.code == exchange.strip().upper())
    total = base.count()
    if total == 0:
        raise HTTPException(404, "No stocks for this sector" + (f" on {exchange}" if exchange else ""))
    pages = max(1, (total + page_size - 1) // page_size)
    if page > pages:
        page = pages
    offset = (page - 1) * page_size
    rows = (
        base.order_by(DbStock.ticker_yf.asc()).offset(offset).limit(page_size).all()
    )
    as_of = datetime.now(timezone.utc).isoformat()
    async with httpx.AsyncClient() as client:
        tasks = [
            _fetch_one(client, r.ticker_yf, r.company_name or r.ticker_yf, stock_id=r.id)
            for r in rows
        ]
        items = list(await asyncio.gather(*tasks))
    ok_n = sum(1 for it in items if not it.error)
    coverage = SectorChartsCoverage(ok=ok_n, total=len(items))
    return SectorEquityChartsResponse(
        sector=sec,
        exchange_filter=exchange.strip().upper() if exchange and exchange.strip() else None,
        page=page,
        page_size=page_size,
        total=total,
        pages=pages,
        as_of=as_of,
        items=items,
        coverage=coverage,
    )
