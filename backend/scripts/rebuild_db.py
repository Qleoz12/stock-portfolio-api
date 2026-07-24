"""
Rebuild stock_unifier.db by copying all readable tables to a fresh database.
Corrupt stock_ohlcv is skipped and recreated empty.

Usage:
  python scripts/rebuild_db.py
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
from config import DB_PATH  # noqa: E402

CREATE_OHLCV_SQL = """
CREATE TABLE stock_ohlcv (
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
CREATE INDEX idx_ohlcv_stock_date ON stock_ohlcv(stock_id, date);
"""

SKIP_TABLES = {"stock_ohlcv", "sqlite_sequence"}


def rebuild(db_path: Path) -> Path:
    backup = db_path.with_suffix(f".bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    shutil.copy2(db_path, backup)
    print(f"Backup: {backup}")

    new_path = db_path.with_suffix(".new.db")
    if new_path.exists():
        new_path.unlink()

    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(new_path))

    src.row_factory = sqlite3.Row
    tables = [
        r[0]
        for r in src.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        if r[0] not in SKIP_TABLES
    ]

    for table in tables:
        try:
            ddl = src.execute(
                f"SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()[0]
            dst.execute(ddl)
            rows = src.execute(f"SELECT * FROM {table}").fetchall()
            if rows:
                cols = rows[0].keys()
                placeholders = ",".join("?" * len(cols))
                col_names = ",".join(cols)
                dst.executemany(
                    f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})",
                    [tuple(r) for r in rows],
                )
            print(f"  copied {table}: {len(rows)} rows")
        except sqlite3.DatabaseError as e:
            print(f"  SKIP {table}: {e}")

    for stmt in CREATE_OHLCV_SQL.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            dst.execute(stmt)
    print("  created stock_ohlcv (empty)")

    dst.commit()
    dst.execute("VACUUM")
    ic = dst.execute("PRAGMA integrity_check").fetchone()[0]
    print(f"  integrity_check: {ic}")
    dst.close()
    src.close()

    db_path.unlink()
    new_path.rename(db_path)
    print(f"Replaced {db_path}")
    return db_path


if __name__ == "__main__":
    rebuild(Path(DB_PATH))
