"""Pluggable market data: Yahoo (yfinance) remains primary; secondary quote fallbacks here."""

from .fallback import secondary_last_close

__all__ = ["secondary_last_close"]
