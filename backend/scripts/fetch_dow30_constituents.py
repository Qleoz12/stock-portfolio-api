"""Refresh backend/data/dow30_constituents.txt from Wikipedia."""
import re
import ssl
import urllib.request
from pathlib import Path

url = "https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average"
req = urllib.request.Request(url, headers={"User-Agent": "stock-portfolio-unifier/1.0"})
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
html = urllib.request.urlopen(req, timeout=30, context=ctx).read().decode("utf-8", errors="ignore")

# Wikipedia table: Symbol column in DJIA components table
syms = re.findall(
    r'<table[^>]*class="wikitable[^"]*"[^>]*>.*?Dow Jones Industrial Average components.*?</table>',
    html,
    re.DOTALL | re.IGNORECASE,
)
if syms:
    block = syms[0]
    tickers = re.findall(r"<td>([A-Z][A-Z0-9.-]{0,8})</td>", block)
else:
    tickers = re.findall(r'data-sort-value="([A-Z][A-Z0-9.-]{0,8})"', html)

# Fallback: known DJIA 30 (March 2024 composition as baseline)
FALLBACK = [
    "AAPL", "AMGN", "AMZN", "AXP", "BA", "CAT", "CRM", "CSCO", "CVX", "DIS",
    "DOW", "GS", "HD", "HON", "IBM", "INTC", "JNJ", "JPM", "KO", "MCD",
    "MMM", "MRK", "MSFT", "NKE", "NVDA", "PG", "TRV", "UNH", "V", "WMT",
]

tickers = sorted({s.replace(".", "-") for s in tickers if 1 <= len(s) <= 6})
if len(tickers) < 25:
    tickers = FALLBACK

out = Path(__file__).resolve().parent.parent / "data" / "dow30_constituents.txt"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(
    "# Dow Jones 30 symbols (one per line). Regenerate: python scripts/fetch_dow30_constituents.py\n"
    + "\n".join(tickers)
    + "\n",
    encoding="utf-8",
)
print(f"wrote {len(tickers)} symbols to {out}")
