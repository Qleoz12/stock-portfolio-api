import os

BASE_DIR = os.path.dirname(__file__)
_REPO_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))


def _load_dotenv_files() -> None:
    """Pick up LIMITLESS_* / DATABASE_* from backend/.env or repo-root .env without requiring python-dotenv."""
    for path in (
        os.path.join(BASE_DIR, ".env"),
        os.path.join(_REPO_ROOT, ".env"),
    ):
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = val
        except OSError:
            continue


_load_dotenv_files()

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(BASE_DIR, "..", ".."))
DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "stock_unifier.db"))
DATABASE_URL = f"sqlite:///{DB_PATH}"
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*").split(",")

# Secondary last-close when Yahoo has no price: auto (try Finnhub then Stooq if keys set) | none
MARKET_DATA_SECONDARY = os.environ.get("MARKET_DATA_SECONDARY", "auto").strip()
# Optional — https://finnhub.io/register
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "").strip()
# Optional — from Stooq CSV download link after captcha (see README)
STOOQ_API_KEY = os.environ.get("STOOQ_API_KEY", "").strip()

# Limitless Exchange — optional https://api.limitless.exchange (prediction markets context on stock detail)
LIMITLESS_API_BASE = os.environ.get("LIMITLESS_API_BASE", "https://api.limitless.exchange").strip().rstrip("/")
LIMITLESS_API_KEY = os.environ.get("LIMITLESS_API_KEY", "").strip()

# Polymarket Gamma API — public read-only market catalog (no API key)
POLYMARKET_GAMMA_BASE = os.environ.get(
    "POLYMARKET_GAMMA_BASE", "https://gamma-api.polymarket.com"
).strip().rstrip("/")

# X/Twitter RSS bridge — Nitter instances (comma-separated), no X API key needed
NITTER_INSTANCES = [
    u.strip().rstrip("/")
    for u in os.environ.get(
        "NITTER_INSTANCES",
        "https://nitter.net,https://nitter.cz",
    ).split(",")
    if u.strip()
]
# Legacy alias — RSSHub Twitter routes are broken on public rsshub.app (404)
RSSHUB_BASE_URL = os.environ.get("RSSHUB_BASE_URL", "https://rsshub.app").strip().rstrip("/")
