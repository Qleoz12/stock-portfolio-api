"""One-off helper to refresh backend/data/sp500_constituents.txt from Wikipedia."""
import re
import ssl
import urllib.request
from pathlib import Path

url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
req = urllib.request.Request(url, headers={"User-Agent": "stock-portfolio-unifier/1.0"})
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
html = urllib.request.urlopen(req, timeout=30, context=ctx).read().decode("utf-8", errors="ignore")
syms = re.findall(r"<td>([A-Z][A-Z0-9.-]{0,8})</td>\s*<td><a", html)
if len(syms) < 400:
    syms = re.findall(r'data-sort-value="([A-Z][A-Z0-9.-]{0,8})"', html)
syms = sorted({s.replace(".", "-") for s in syms if 1 <= len(s) <= 6})
out = Path(__file__).resolve().parent.parent / "data" / "sp500_constituents.txt"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(
    "# S&P 500 symbols (one per line). Regenerate: python scripts/fetch_sp500_constituents.py\n"
    + "\n".join(syms)
    + "\n",
    encoding="utf-8",
)
print(f"wrote {len(syms)} symbols to {out}")
