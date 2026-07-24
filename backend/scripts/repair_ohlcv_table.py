"""
Repair corrupted stock_ohlcv table in stock_unifier.db.

Drops and recreates the table, then optionally re-downloads OHLCV for tickers.

Usage:
  python scripts/repair_ohlcv_table.py
  python scripts/repair_ohlcv_table.py --tickers AAPL MSFT --period 1y
  python scripts/repair_ohlcv_table.py --universe dow30
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from config import DB_PATH  # noqa: E402

CREATE_OHLCV_SQL = """
CREATE TABLE IF NOT EXISTS stock_ohlcv (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_id INTEGER NOT NULL,
    date DATE NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume REAL,
    FOREIGN KEY(stock_id) REFERENCES stocks(id),
    UNIQUE(stock_id, date)
);
CREATE INDEX IF NOT EXISTS idx_ohlcv_stock_date ON stock_ohlcv(stock_id, date);
"""


def _load_universe_tickers(universe: str) -> list[str]:
    data_dir = BACKEND_DIR / "data"
    if universe == "dow30":
        path = data_dir / "dow30_constituents.txt"
    elif universe == "sp500":
        path = data_dir / "sp500_constituents.txt"
    else:
        raise ValueError(f"Unknown universe: {universe}")
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")]


def repair_table(db_path: Path) -> dict:
    """Drop corrupt stock_ohlcv and recreate empty table."""
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    result = {"dropped": False, "recreated": False, "vacuumed": False}
    try:
        cur.execute("SELECT COUNT(*) FROM stock_ohlcv")
        result["old_rows"] = cur.fetchone()[0]
        cur.execute("DROP TABLE IF EXISTS stock_ohlcv")
        result["dropped"] = True
    except sqlite3.DatabaseError:
        cur.execute("DROP TABLE IF EXISTS stock_ohlcv")
        result["dropped"] = True
        result["old_rows"] = "unreadable"
    for stmt in CREATE_OHLCV_SQL.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            cur.execute(stmt)
    result["recreated"] = True
    conn.commit()
    conn.execute("VACUUM")
    result["vacuumed"] = True
    ic = conn.execute("PRAGMA integrity_check").fetchone()[0]
    result["integrity_check"] = ic
    conn.close()
    return result


def fetch_ohlcv_for_tickers(db_path: Path, tickers: list[str], period_days: int = 365) -> dict:
    """Download OHLCV from yfinance and insert into repaired table."""
    import yfinance as yf
    from sqlalchemy.orm import Session
    from database import SessionLocal
    from models import Stock, StockOHLCV
    from routers.charts import _flatten_yfinance_hist

    db: Session = SessionLocal()
    today = date.today()
    start = today - timedelta(days=period_days)
    stats = {"tickers": len(tickers), "rows_added": 0, "errors": []}

    try:
        for ticker in tickers:
            stock = db.query(Stock).filter(Stock.ticker_yf == ticker).first()
            if not stock:
                stats["errors"].append(f"{ticker}: not in DB")
                continue
            try:
                hist = yf.download(
                    ticker,
                    start=start.isoformat(),
                    end=(today + timedelta(days=1)).isoformat(),
                    progress=False,
                    timeout=20,
                    auto_adjust=False,
                )
            except Exception as e:
                stats["errors"].append(f"{ticker}: download failed ({e})")
                continue
            if hist is None or hist.empty:
                stats["errors"].append(f"{ticker}: empty history")
                continue
            hist = _flatten_yfinance_hist(hist)
            col_map = {str(c).lower(): c for c in hist.columns}
            added = 0
            for idx, row in hist.iterrows():
                d = idx.date() if hasattr(idx, "date") else idx
                c = float(row.get(col_map.get("close", "Close"), 0) or 0)
                if c == 0:
                    continue
                existing = db.query(StockOHLCV).filter_by(stock_id=stock.id, date=d).first()
                if existing:
                    continue
                db.add(
                    StockOHLCV(
                        stock_id=stock.id,
                        date=d,
                        open=float(row.get(col_map.get("open", "Open"), 0) or 0),
                        high=float(row.get(col_map.get("high", "High"), 0) or 0),
                        low=float(row.get(col_map.get("low", "Low"), 0) or 0),
                        close=c,
                        volume=float(row.get(col_map.get("volume", "Volume"), 0) or 0),
                    )
                )
                added += 1
            db.commit()
            stats["rows_added"] += added
    finally:
        db.close()
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description="Repair corrupted stock_ohlcv table")
    ap.add_argument("--db", type=Path, default=Path(DB_PATH))
    ap.add_argument("--tickers", nargs="*", help="Tickers to re-download after repair")
    ap.add_argument("--universe", choices=["dow30", "sp500"], help="Load tickers from universe file")
    ap.add_argument("--period", type=int, default=365, help="Days of history to download")
    args = ap.parse_args()

    print(f"Repairing OHLCV table in {args.db}...")
    result = repair_table(args.db)
    print(f"  dropped={result['dropped']} recreated={result['recreated']} vacuum={result['vacuumed']}")
    print(f"  integrity_check: {result.get('integrity_check')}")

    tickers = list(args.tickers or [])
    if args.universe:
        tickers.extend(_load_universe_tickers(args.universe))
    tickers = sorted(set(tickers))

    if tickers:
        print(f"Downloading OHLCV for {len(tickers)} tickers ({args.period}d)...")
        stats = fetch_ohlcv_for_tickers(args.db, tickers, args.period)
        print(f"  rows_added={stats['rows_added']} errors={len(stats['errors'])}")
        for err in stats["errors"][:10]:
            print(f"    {err}")


if __name__ == "__main__":
    main()
