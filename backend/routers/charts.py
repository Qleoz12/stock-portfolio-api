from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from pydantic import BaseModel
from datetime import date, datetime, timedelta
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from database import get_db
from models import Stock, StockOHLCV, ChartDrawing, StockFeature
from logger import get_logger

log = get_logger("charts")

_OHLC_LEVEL_NAMES = frozenset(
    {"open", "high", "low", "close", "adj close", "volume"}
)


def _flatten_yfinance_hist(hist):
    """Pick the correct MultiIndex level (Price vs Ticker) so OHLC columns stay named Open/High/…"""
    if hist is None or hist.empty:
        return hist
    if getattr(hist.columns, "nlevels", 1) <= 1:
        return hist
    lev0 = {str(x).lower() for x in hist.columns.get_level_values(0)}
    lev1 = {str(x).lower() for x in hist.columns.get_level_values(1)}
    n0 = sum(1 for x in lev0 if x in _OHLC_LEVEL_NAMES)
    n1 = sum(1 for x in lev1 if x in _OHLC_LEVEL_NAMES)
    if n0 >= 3 and n1 < n0:
        return hist.droplevel(1, axis=1)
    if n1 >= 3 and n0 < n1:
        return hist.droplevel(0, axis=1)
    return hist.droplevel(1, axis=1)


def _spot_last_close_yahoo(ticker_yf: str):
    import yfinance as yf

    try:
        h = yf.download(
            ticker_yf,
            period="5d",
            progress=False,
            timeout=15,
            auto_adjust=False,
        )
    except Exception as e:
        log.debug("spot Yahoo close failed for %s: %s", ticker_yf, e)
        return None
    if h is None or h.empty:
        return None
    h = _flatten_yfinance_hist(h)
    if "Close" not in h.columns:
        return None
    close = h["Close"].dropna()
    if hasattr(close, "columns"):
        close = close.iloc[:, 0]
    if close.empty:
        return None
    return float(close.iloc[-1])


def _ohlcv_cache_disagrees_with_yahoo(stock: Stock, db: Session) -> bool:
    """True if the latest cached bar is far from live Yahoo (bad cache / wrong columns / stale mix)."""
    last_bar = (
        db.query(StockOHLCV)
        .filter(StockOHLCV.stock_id == stock.id)
        .order_by(StockOHLCV.date.desc())
        .first()
    )
    if not last_bar or not last_bar.close:
        return False

    feat = db.query(StockFeature).filter_by(stock_id=stock.id).first()
    if feat and feat.last_close:
        lc, fc = float(last_bar.close), float(feat.last_close)
        if lc > 0 and fc > 0 and max(lc, fc) / min(lc, fc) <= 1.25:
            return False

    y = _spot_last_close_yahoo(stock.ticker_yf)
    if y is None or last_bar.close <= 0:
        return False
    return max(y, float(last_bar.close)) / min(y, float(last_bar.close)) > 5.0

router = APIRouter(prefix="/api/stocks", tags=["charts"])

PERIOD_DAYS = {
    "1m": 30, "3m": 90, "6m": 180,
    "1y": 365, "2y": 730, "5y": 1825,
}


def _ensure_ohlcv_cache(stock: Stock, db: Session):
    """Download OHLCV from yfinance if cache is stale or empty."""
    import yfinance as yf

    last_cached = db.query(func.max(StockOHLCV.date)).filter(
        StockOHLCV.stock_id == stock.id
    ).scalar()

    today = date.today()

    meta = (
        db.query(
            func.count(StockOHLCV.id),
            func.min(StockOHLCV.date),
            func.max(StockOHLCV.date),
        )
        .filter(StockOHLCV.stock_id == stock.id)
        .one()
    )
    row_count, min_d, max_d = int(meta[0] or 0), meta[1], meta[2]
    span_days = (max_d - min_d).days if min_d and max_d else 0
    # Evita "una sola vela": antes se salía si el último día era reciente aunque hubiera <~3 meses de historia.
    adequate = row_count >= 60 and span_days >= 120

    if row_count > 0 and _ohlcv_cache_disagrees_with_yahoo(stock, db):
        deleted = (
            db.query(StockOHLCV)
            .filter(StockOHLCV.stock_id == stock.id)
            .delete(synchronize_session=False)
        )
        db.commit()
        log.warning(
            "OHLCV: removed %s cached rows for %s (latest close out of band vs Yahoo)",
            deleted,
            stock.ticker_yf,
        )
        last_cached = None
        adequate = False

    if last_cached and (today - last_cached).days <= 1 and adequate:
        return

    if not adequate:
        start = today - timedelta(days=1825)
    elif last_cached:
        start = last_cached + timedelta(days=1)
    else:
        start = today - timedelta(days=1825)

    try:
        hist = yf.download(
            stock.ticker_yf,
            start=start.isoformat(),
            end=(today + timedelta(days=1)).isoformat(),
            progress=False,
            timeout=20,
            auto_adjust=False,
        )
    except Exception as e:
        log.warning("OHLCV yfinance error for %s: %s", stock.ticker_yf, e)
        return

    if hist is None or hist.empty:
        return

    hist = _flatten_yfinance_hist(hist)

    col_map = {}
    for col in hist.columns:
        col_map[col.lower()] = col

    rows_added = 0
    for idx, row in hist.iterrows():
        d = idx.date() if hasattr(idx, 'date') else idx
        o = float(row.get(col_map.get("open", "Open"), 0) or 0)
        h = float(row.get(col_map.get("high", "High"), 0) or 0)
        lo = float(row.get(col_map.get("low", "Low"), 0) or 0)
        c = float(row.get(col_map.get("close", "Close"), 0) or 0)
        v = float(row.get(col_map.get("volume", "Volume"), 0) or 0)

        if c == 0 and h == 0:
            continue

        existing = db.query(StockOHLCV).filter_by(stock_id=stock.id, date=d).first()
        if existing:
            existing.open = o
            existing.high = h
            existing.low = lo
            existing.close = c
            existing.volume = v
        else:
            db.add(StockOHLCV(
                stock_id=stock.id, date=d,
                open=o, high=h, low=lo, close=c, volume=v,
            ))
            rows_added += 1

    db.commit()
    log.info("OHLCV %s: cached %d new rows (from %s)", stock.ticker_yf, rows_added, start)


@router.get("/{stock_id}/ohlcv")
def get_ohlcv(
    stock_id: int,
    period: str = Query("1y", description="1m, 3m, 6m, 1y, 2y, 5y"),
    db: Session = Depends(get_db),
):
    stock = db.query(Stock).filter(Stock.id == stock_id).first()
    if not stock:
        raise HTTPException(status_code=404, detail="Stock not found")

    _ensure_ohlcv_cache(stock, db)

    days = PERIOD_DAYS.get(period, 365)
    cutoff = date.today() - timedelta(days=days)

    rows = (
        db.query(StockOHLCV)
        .filter(StockOHLCV.stock_id == stock_id, StockOHLCV.date >= cutoff)
        .order_by(StockOHLCV.date.asc())
        .all()
    )

    return {
        "ticker_yf": stock.ticker_yf,
        "count": len(rows),
        "data": [
            {
                "date": r.date.isoformat(),
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
            }
            for r in rows
        ],
    }


class DrawingCreate(BaseModel):
    drawing_type: str
    price1: float
    price2: Optional[float] = None
    date1: Optional[str] = None
    date2: Optional[str] = None
    color: str = "#facc15"
    label: str = ""


class DrawingUpdate(BaseModel):
    price1: Optional[float] = None
    price2: Optional[float] = None
    date1: Optional[str] = None
    date2: Optional[str] = None
    color: Optional[str] = None
    label: Optional[str] = None


@router.get("/{stock_id}/drawings")
def list_drawings(stock_id: int, db: Session = Depends(get_db)):
    drawings = db.query(ChartDrawing).filter(
        ChartDrawing.stock_id == stock_id
    ).order_by(ChartDrawing.created_at.asc()).all()

    return [
        {
            "id": d.id,
            "drawing_type": d.drawing_type,
            "price1": d.price1,
            "price2": d.price2,
            "date1": d.date1,
            "date2": d.date2,
            "color": d.color,
            "label": d.label,
        }
        for d in drawings
    ]


@router.post("/{stock_id}/drawings", status_code=201)
def create_drawing(stock_id: int, data: DrawingCreate, db: Session = Depends(get_db)):
    stock = db.query(Stock).filter(Stock.id == stock_id).first()
    if not stock:
        raise HTTPException(status_code=404, detail="Stock not found")

    if data.drawing_type not in ("hline", "trendline"):
        raise HTTPException(status_code=400, detail="drawing_type must be 'hline' or 'trendline'")

    drawing = ChartDrawing(
        stock_id=stock_id,
        drawing_type=data.drawing_type,
        price1=data.price1,
        price2=data.price2,
        date1=data.date1,
        date2=data.date2,
        color=data.color,
        label=data.label,
    )
    db.add(drawing)
    db.commit()
    db.refresh(drawing)

    return {
        "id": drawing.id,
        "drawing_type": drawing.drawing_type,
        "price1": drawing.price1,
        "price2": drawing.price2,
        "date1": drawing.date1,
        "date2": drawing.date2,
        "color": drawing.color,
        "label": drawing.label,
    }


@router.put("/{stock_id}/drawings/{drawing_id}")
def update_drawing(stock_id: int, drawing_id: int, data: DrawingUpdate, db: Session = Depends(get_db)):
    drawing = db.query(ChartDrawing).filter(
        ChartDrawing.id == drawing_id, ChartDrawing.stock_id == stock_id
    ).first()
    if not drawing:
        raise HTTPException(status_code=404, detail="Drawing not found")

    if data.price1 is not None:
        drawing.price1 = data.price1
    if data.price2 is not None:
        drawing.price2 = data.price2
    if data.date1 is not None:
        drawing.date1 = data.date1
    if data.date2 is not None:
        drawing.date2 = data.date2
    if data.color is not None:
        drawing.color = data.color
    if data.label is not None:
        drawing.label = data.label

    db.commit()
    return {
        "id": drawing.id,
        "drawing_type": drawing.drawing_type,
        "price1": drawing.price1,
        "price2": drawing.price2,
        "date1": drawing.date1,
        "date2": drawing.date2,
        "color": drawing.color,
        "label": drawing.label,
    }


@router.delete("/{stock_id}/drawings/{drawing_id}", status_code=204)
def delete_drawing(stock_id: int, drawing_id: int, db: Session = Depends(get_db)):
    drawing = db.query(ChartDrawing).filter(
        ChartDrawing.id == drawing_id, ChartDrawing.stock_id == stock_id
    ).first()
    if not drawing:
        raise HTTPException(status_code=404, detail="Drawing not found")

    db.delete(drawing)
    db.commit()
