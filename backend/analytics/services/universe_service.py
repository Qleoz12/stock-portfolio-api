"""Universe management service."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from analytics.data.loaders import load_constituents_file, load_universe_tickers
from analytics.models.universe import Universe, UniverseCreate, UniverseType
from models import Portfolio


class UniverseService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_universes(self) -> list[Universe]:
        universes = [
            Universe(
                id="dow30",
                name="Dow Jones 30",
                description="Dow Jones Industrial Average components",
                universe_type=UniverseType.INDEX,
                tickers=load_constituents_file("dow30_constituents.txt"),
                source="system",
                owner="system",
                benchmark="^DJI",
            ),
            Universe(
                id="sp500",
                name="S&P 500",
                description="S&P 500 constituents",
                universe_type=UniverseType.INDEX,
                tickers=load_constituents_file("sp500_constituents.txt"),
                source="system",
                owner="system",
                benchmark="^GSPC",
            ),
        ]
        portfolios = self.db.query(Portfolio).all()
        for p in portfolios:
            tickers = load_universe_tickers(f"portfolio_{p.id}", self.db)
            universes.append(
                Universe(
                    id=f"portfolio_{p.id}",
                    name=p.name,
                    description=p.description or "",
                    universe_type=UniverseType.PORTFOLIO,
                    tickers=tickers,
                    source="user_portfolio",
                    owner="user",
                )
            )
        return universes

    def get_universe(self, universe_id: str) -> Optional[Universe]:
        for u in self.list_universes():
            if u.id == universe_id:
                return u
        return None

    def resolve_tickers(self, universe_id: str, override: Optional[list[str]] = None) -> list[str]:
        if override:
            return sorted(set(override))
        return load_universe_tickers(universe_id, self.db)

    def create_universe(self, data: UniverseCreate) -> Universe:
        uid = f"custom_{int(datetime.utcnow().timestamp())}"
        return Universe(
            id=uid,
            name=data.name,
            description=data.description,
            universe_type=data.universe_type,
            tickers=sorted(set(data.tickers)),
            source=data.source,
            owner="user",
            benchmark=data.benchmark,
            created_at=datetime.utcnow(),
        )
