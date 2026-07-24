import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from logger import setup_root_logging, get_logger
setup_root_logging()
log = get_logger("main")

import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from database import engine
from models import Base

Base.metadata.create_all(bind=engine)


def _ensure_sqlite_columns():
    """Add columns added after first deploy (SQLite has no ALTER in create_all)."""
    from sqlalchemy import text

    if not str(engine.url).startswith("sqlite"):
        return
    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(stock_features)")).fetchall()
        cols = {row[1] for row in rows}
        if "day_change_pct" not in cols:
            conn.execute(text("ALTER TABLE stock_features ADD COLUMN day_change_pct FLOAT"))
            log.info("Migration: stock_features.day_change_pct added")
        stock_rows = conn.execute(text("PRAGMA table_info(stocks)")).fetchall()
        stock_cols = {row[1] for row in stock_rows}
        if "possible_value_trap" not in stock_cols:
            conn.execute(
                text("ALTER TABLE stocks ADD COLUMN possible_value_trap BOOLEAN NOT NULL DEFAULT 0")
            )
            log.info("Migration: stocks.possible_value_trap added")
        note_rows = conn.execute(text("PRAGMA table_info(dividend_calendar_notes)")).fetchall()
        note_cols = {row[1] for row in note_rows}
        if note_rows and "title" not in note_cols:
            conn.execute(text("ALTER TABLE dividend_calendar_notes ADD COLUMN title VARCHAR(255) DEFAULT ''"))
            log.info("Migration: dividend_calendar_notes.title added")
        if note_rows and "updated_at" not in note_cols:
            conn.execute(text("ALTER TABLE dividend_calendar_notes ADD COLUMN updated_at DATETIME"))
            log.info("Migration: dividend_calendar_notes.updated_at added")


_ensure_sqlite_columns()
log.info("Database tables ready")

app = FastAPI(title="Stock Portfolio Unifier", version="1.0.0")

from config import CORS_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class APILoggingMiddleware(BaseHTTPMiddleware):
    """Rotating api.log: timestamp, method, path, status, duration; failures include traceback."""

    async def dispatch(self, request: Request, call_next):
        api_log = get_logger("api.http")
        start = time.perf_counter()
        path = request.url.path
        method = request.method
        q = request.url.query
        if q:
            path = f"{path}?{q}"
        try:
            response = await call_next(request)
            elapsed_ms = (time.perf_counter() - start) * 1000
            status = response.status_code
            line = f"{method} {path} -> {status} | {elapsed_ms:.1f}ms"
            if status >= 500:
                api_log.error(line)
            elif status >= 400:
                api_log.warning(line)
            else:
                api_log.info(line)
            return response
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start) * 1000
            api_log.exception("%s %s FAILED after %.1fms: %s", method, path, elapsed_ms, e)
            raise


app.add_middleware(APILoggingMiddleware)

from routers.stocks import router as stocks_router
from routers.portfolios import router as portfolios_router
from routers.dividends import router as dividends_router
from routers.analytics import router as analytics_router
from routers.charts import router as charts_router
from routers.arbitrage import router as arbitrage_router
from routers.fair_value import router as fair_value_router
from routers.limitless import router as limitless_router
from routers.polymarket import router as polymarket_router
from routers.prediction_compare import router as prediction_compare_router
from routers.market_charts import router as market_charts_router
from routers.x_feeds import router as x_feeds_router
from routers.news_sentiment import router as news_sentiment_router
from routers.valuation import router as valuation_router
from routers.journal import router as journal_router
from routers.forex import router as forex_router
from routers.cluster_explorer import router as cluster_router

app.include_router(stocks_router)
app.include_router(portfolios_router)
app.include_router(dividends_router)
app.include_router(analytics_router)
app.include_router(charts_router)
app.include_router(arbitrage_router)
app.include_router(fair_value_router)
app.include_router(limitless_router)
app.include_router(polymarket_router)
app.include_router(prediction_compare_router)
app.include_router(market_charts_router)
app.include_router(x_feeds_router)
app.include_router(news_sentiment_router)
app.include_router(valuation_router)
app.include_router(journal_router)
app.include_router(forex_router)
app.include_router(cluster_router)


@app.get("/api/health")
def health():
    from sqlalchemy import text
    from database import SessionLocal
    db = SessionLocal()
    try:
        result = db.execute(text("SELECT COUNT(*) FROM stocks")).scalar()
        return {"status": "ok", "stocks_count": result}
    except Exception:
        return {"status": "ok", "stocks_count": 0, "note": "DB may need ETL run"}
    finally:
        db.close()


@app.post("/api/etl/run")
def run_etl():
    from etl.load_features import run as run_features
    from etl.load_div_events import run as run_divs
    from etl.load_quanfury import run as run_quanfury
    results = {}
    try:
        run_features()
        results["features"] = "ok"
    except Exception as e:
        results["features"] = str(e)
    try:
        run_divs()
        results["div_events"] = "ok"
    except Exception as e:
        results["div_events"] = str(e)
    try:
        run_quanfury()
        results["quanfury"] = "ok"
    except Exception as e:
        results["quanfury"] = str(e)
    return {"status": "completed", "results": results}


@app.get("/api/export/stocks")
def export_stocks_csv():
    import csv
    import io
    from fastapi.responses import StreamingResponse
    from database import SessionLocal
    from models import Stock, StockFeature, Exchange
    db = SessionLocal()
    try:
        stocks = db.query(Stock, StockFeature, Exchange).outerjoin(
            StockFeature, Stock.id == StockFeature.stock_id
        ).outerjoin(Exchange, Stock.exchange_id == Exchange.id).all()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ticker_yf", "symbol", "company_name", "exchange", "sector", "currency",
                          "last_close", "div_yield_ttm", "dividend_ttm", "rsi_14", "is_quanfury"])
        for s, f, e in stocks:
            writer.writerow([s.ticker_yf, s.symbol, s.company_name, e.code if e else "", s.sector,
                              s.currency, f.last_close if f else "", f.div_yield_ttm if f else "",
                              f.dividend_ttm if f else "", f.rsi_14 if f else "", s.is_quanfury_available])
        output.seek(0)
        return StreamingResponse(iter([output.getvalue()]), media_type="text/csv",
                                  headers={"Content-Disposition": "attachment; filename=stocks_export.csv"})
    finally:
        db.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
