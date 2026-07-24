"""Universe domain models."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class UniverseType(str, Enum):
    INDEX = "index"
    SECTOR = "sector"
    ETF = "etf"
    PORTFOLIO = "portfolio"
    WATCHLIST = "watchlist"
    CUSTOM = "custom"
    FILE = "file"


class Universe(BaseModel):
    id: str
    name: str
    description: str = ""
    universe_type: UniverseType = UniverseType.CUSTOM
    benchmark: str = "^GSPC"
    currency: str = "USD"
    tickers: list[str] = Field(default_factory=list)
    source: str = "user"
    owner: str = "user"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class UniverseCreate(BaseModel):
    name: str
    description: str = ""
    universe_type: UniverseType = UniverseType.CUSTOM
    tickers: list[str]
    benchmark: str = "^GSPC"
    source: str = "user"
