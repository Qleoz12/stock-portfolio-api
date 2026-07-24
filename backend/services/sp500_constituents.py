"""Load S&P 500 constituent symbols from backend/data/sp500_constituents.txt."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "sp500_constituents.txt"


@lru_cache(maxsize=1)
def sp500_symbols() -> frozenset[str]:
    if not _DATA_FILE.is_file():
        return frozenset()
    out: set[str] = set()
    for line in _DATA_FILE.read_text(encoding="utf-8").splitlines():
        sym = line.strip().upper().split("#", 1)[0].strip()
        if sym and sym != "SYMBOL":
            out.add(sym)
    return frozenset(out)
