"""
Forex dashboard — Yahoo FX pairs + arbitrage reference rates for LatAm (Colombia-focused).
"""
from __future__ import annotations

import asyncio
import sys
import os
from datetime import datetime, timezone
from typing import Literal

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field

from logger import get_logger
from routers.market_charts import SectorChartItem, _fetch_one

log = get_logger("routers.forex")

router = APIRouter(prefix="/api/forex", tags=["forex"])

ForexRegion = Literal["colombia", "latam", "north", "global"]


class ForexPairMeta(BaseModel):
    yahoo: str
    pair: str
    label: str
    region: ForexRegion
    primary: bool = False
    note: str = ""


class ForexCrossRate(BaseModel):
    pair: str
    label: str
    rate: float | None
    formula: str


class ForexP2PRef(BaseModel):
    pair: str
    avg_mid: float | None
    sources_count: int
    note: str


class ForexDashboardResponse(BaseModel):
    as_of: str
    source: str = "yahoo_chart_v8"
    items: list[SectorChartItem]
    primary_pairs: list[str]
    crosses: list[ForexCrossRate] = Field(default_factory=list)
    p2p_refs: list[ForexP2PRef] = Field(default_factory=list)
    colombia_tips: list[str] = Field(default_factory=list)


FOREX_UNIVERSE: list[ForexPairMeta] = [
    ForexPairMeta(
        yahoo="USDCOP=X",
        pair="USD/COP",
        label="Dólar / Peso colombiano",
        region="colombia",
        primary=True,
        note="Par local. Spot Yahoo; para compra P2P de USDT en COP ver Arbitrage.",
    ),
    ForexPairMeta(
        yahoo="USDMXN=X",
        pair="USD/MXN",
        label="Dólar / Peso mexicano",
        region="latam",
        primary=True,
        note="Referencia LatAm; Bitso (MXN) también en Arbitrage.",
    ),
    ForexPairMeta(
        yahoo="USDCAD=X",
        pair="USD/CAD",
        label="Dólar / Dólar canadiense",
        region="north",
        primary=True,
        note="Útil para carry y comparar con COP/CAD.",
    ),
    ForexPairMeta(
        yahoo="USDCLP=X",
        pair="USD/CLP",
        label="Dólar / Peso chileno",
        region="latam",
        note="Vecino Andino; contexto regional.",
    ),
    ForexPairMeta(
        yahoo="USDBRL=X",
        pair="USD/BRL",
        label="Dólar / Real brasileño",
        region="latam",
        note="Mayor economía LatAm.",
    ),
    ForexPairMeta(
        yahoo="USDARS=X",
        pair="USD/ARS",
        label="Dólar / Peso argentino",
        region="latam",
        note="Alta volatilidad; CriptoYa USDT/ARS en Arbitrage.",
    ),
    ForexPairMeta(
        yahoo="EURUSD=X",
        pair="EUR/USD",
        label="Euro / Dólar",
        region="global",
        note="Referencia global del dólar.",
    ),
    ForexPairMeta(
        yahoo="GBPUSD=X",
        pair="GBP/USD",
        label="Libra / Dólar",
        region="global",
        note="Referencia FX mayor.",
    ),
]

COLOMBIA_TIPS = [
    "Tu par base es USD/COP: cotización spot vía Yahoo y tipo P2P USDT/COP en Arbitrage (Binance P2P, CriptoYa).",
    "USD/MXN y USD/CAD sirven como referencia regional y para cruces COP/MXN y COP/CAD calculados abajo.",
    "Acciones colombianas en la app usan COP (.BO en BVC) o ADRs en USD (CIB, EC, AVAL) — el FX afecta la lectura de ambos.",
    "Para convertir pesos a crypto estable: revisa USDT/COP en Arbitrage → P2P Book (COP).",
]


def _avg_mid_for_pair(by_pair: dict[str, list], pair: str) -> tuple[float | None, int]:
    entries = by_pair.get(pair, [])
    prices = [
        e.get("mid") or e.get("ask") or e.get("bid")
        for e in entries
        if (e.get("mid") or e.get("ask") or e.get("bid"))
    ]
    if not prices:
        return None, 0
    return sum(prices) / len(prices), len(entries)


def _derive_crosses(last_by_pair: dict[str, float | None]) -> list[ForexCrossRate]:
    usd_cop = last_by_pair.get("USD/COP")
    usd_mxn = last_by_pair.get("USD/MXN")
    usd_cad = last_by_pair.get("USD/CAD")
    usd_clp = last_by_pair.get("USD/CLP")
    out: list[ForexCrossRate] = []

    if usd_cop and usd_mxn and usd_mxn > 0:
        out.append(
            ForexCrossRate(
                pair="COP/MXN",
                label="Pesos colombianos por 1 peso mexicano",
                rate=round(usd_cop / usd_mxn, 4),
                formula="USD/COP ÷ USD/MXN",
            )
        )
    if usd_cop and usd_cad and usd_cad > 0:
        out.append(
            ForexCrossRate(
                pair="COP/CAD",
                label="Pesos colombianos por 1 dólar canadiense",
                rate=round(usd_cop / usd_cad, 2),
                formula="USD/COP ÷ USD/CAD",
            )
        )
    if usd_cop and usd_clp and usd_clp > 0:
        out.append(
            ForexCrossRate(
                pair="COP/CLP",
                label="Pesos colombianos por 1 peso chileno",
                rate=round(usd_cop / usd_clp, 6),
                formula="USD/COP ÷ USD/CLP",
            )
        )
    return out


@router.get("/dashboard", response_model=ForexDashboardResponse)
async def forex_dashboard():
    """Yahoo daily FX series + P2P refs from arbitrage module."""
    async with httpx.AsyncClient() as client:
        tasks = [
            _fetch_one(client, m.yahoo, m.label)
            for m in FOREX_UNIVERSE
        ]
        results = await asyncio.gather(*tasks)

    last_by_pair: dict[str, float | None] = {}
    for meta, item in zip(FOREX_UNIVERSE, results):
        last_by_pair[meta.pair] = item.last

    p2p_refs: list[ForexP2PRef] = []
    try:
        from routers.arbitrage import fetch_all_rates

        raw = await fetch_all_rates()
        by_pair: dict[str, list] = {}
        for r in raw:
            by_pair.setdefault(r["pair"], []).append(r)
        for pair, note in [
            ("USDT/COP", "Precio promedio USDT en pesos (P2P / agregadores)"),
            ("USD/COP", "Tipo oficial aprox. (ExchangeRate-API)"),
            ("USD/MXN", "USD/MXN vía Bitso u otras fuentes arbitrage"),
        ]:
            avg, n = _avg_mid_for_pair(by_pair, pair)
            if avg is not None:
                p2p_refs.append(
                    ForexP2PRef(pair=pair, avg_mid=round(avg, 4), sources_count=n, note=note)
                )
    except Exception as e:
        log.warning("forex p2p refs failed: %s", e)

    return ForexDashboardResponse(
        as_of=datetime.now(timezone.utc).isoformat(),
        items=results,
        primary_pairs=[m.pair for m in FOREX_UNIVERSE if m.primary],
        crosses=_derive_crosses(last_by_pair),
        p2p_refs=p2p_refs,
        colombia_tips=COLOMBIA_TIPS,
    )


@router.get("/pairs", response_model=list[ForexPairMeta])
def forex_pairs_catalog():
    """Metadata for all supported FX pairs in the dashboard."""
    return FOREX_UNIVERSE
