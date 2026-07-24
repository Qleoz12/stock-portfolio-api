"""
Map Yahoo Finance tickers to provider-specific symbols.

Stooq uses lowercase `symbol.xx` suffixes (see https://stooq.com/db/h/).
"""

# Yahoo suffix (lower) -> Stooq file suffix (lower)
YAHOO_TO_STOOQ_SUFFIX: dict[str, str] = {
    "to": "to",
    "v": "v",
    "l": "uk",  # LSE on Yahoo → Stooq typically .uk
    "pa": "pa",
    "de": "de",
    "ax": "ax",
    "hk": "hk",
    "sw": "sw",
    "as": "as",
    "mi": "mi",
    "in": "in",
    "ns": "ns",
    "sa": "sa",
    "wa": "wa",  # Warsaw
    "f": "f",  # Frankfurt sometimes .f on Yahoo
    "co": "co",  # Copenhagen
    "ol": "ol",  # Oslo
    "he": "he",  # Helsinki
    "ta": "ta",  # Tel Aviv
}


def yahoo_to_stooq_symbol(ticker_yf: str) -> str:
    """
    Convert a Yahoo ticker to Stooq daily symbol (e.g. MSFT → msft.us, SHOP.TO → shop.to).
    Unknown international suffixes are passed through lowercased.
    """
    raw = (ticker_yf or "").strip()
    if not raw:
        return raw
    lower = raw.lower()
    if "." not in lower:
        return f"{lower}.us"
    base, suf = lower.rsplit(".", 1)
    mapped = YAHOO_TO_STOOQ_SUFFIX.get(suf)
    if mapped is not None:
        return f"{base}.{mapped}"
    return f"{base}.{suf}"
