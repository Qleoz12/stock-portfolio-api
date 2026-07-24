"""Unified journal / bitácora hub — aggregates notes from dividends, portfolios, arbitrage, and free entries."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models import (
    ArbitrageOperation,
    DividendCalendarNote,
    JournalEntry,
    ManualCalendarDividend,
    Portfolio,
    PortfolioSnapshot,
)

router = APIRouter(prefix="/api/journal", tags=["journal"])

JournalSource = Literal[
    "dividend_calendar",
    "manual_dividend",
    "portfolio_snapshot",
    "arbitrage_operation",
    "journal",
]


def _parse_date_param(val: Optional[str], default: date) -> date:
    if not val:
        return default
    try:
        return datetime.strptime(val.strip()[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return default


def _iso_dt(dt: Optional[datetime]) -> str:
    if dt is None:
        return ""
    if getattr(dt, "tzinfo", None) is not None:
        return dt.isoformat()
    return dt.isoformat() + "Z"


class JournalHubItem(BaseModel):
    key: str
    source: JournalSource
    source_id: int
    target_date: str
    title: Optional[str] = None
    body: str
    context_label: str
    context_href: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None
    can_edit_date: bool = False
    can_delete: bool = False


class JournalEntryCreate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    body: str = Field(..., min_length=1, max_length=8000)
    target_date: str


class JournalEntryPatch(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    body: Optional[str] = Field(default=None, min_length=1, max_length=8000)
    target_date: Optional[str] = None


class DividendCalendarNotePatch(BaseModel):
    note_date: Optional[str] = None
    title: Optional[str] = Field(default=None, max_length=255)
    body: Optional[str] = Field(default=None, min_length=1, max_length=8000)


class NoteBodyPatch(BaseModel):
    body: str = Field(..., min_length=1, max_length=8000)


def _hub_item_from_dividend_note(r: DividendCalendarNote) -> JournalHubItem:
    title = (r.title or "").strip() or None
    return JournalHubItem(
        key=f"dividend_calendar:{r.id}",
        source="dividend_calendar",
        source_id=r.id,
        target_date=str(r.note_date),
        title=title,
        body=r.body or "",
        context_label=f"Dividendos · {r.note_date}",
        context_href="/dividends",
        created_at=_iso_dt(r.created_at),
        updated_at=_iso_dt(r.updated_at) or None,
        can_edit_date=True,
        can_delete=True,
    )


def _hub_item_from_manual(m: ManualCalendarDividend) -> JournalHubItem:
    note = (m.note or "").strip()
    return JournalHubItem(
        key=f"manual_dividend:{m.id}",
        source="manual_dividend",
        source_id=m.id,
        target_date=str(m.div_date),
        title=m.ticker_yf,
        body=note,
        context_label=f"Dividendo manual · {m.ticker_yf} · {m.div_date}",
        context_href="/dividends",
        created_at=_iso_dt(m.created_at),
        updated_at=None,
        can_edit_date=False,
        can_delete=False,
    )


def _hub_item_from_snapshot(s: PortfolioSnapshot, portfolio: Optional[Portfolio]) -> JournalHubItem:
    notes = (s.notes or "").strip()
    td = date(s.year, s.month, 1)
    pname = portfolio.name if portfolio else f"Portfolio #{s.portfolio_id}"
    month_names = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    mlabel = month_names[s.month] if 1 <= s.month <= 12 else str(s.month)
    return JournalHubItem(
        key=f"portfolio_snapshot:{s.id}",
        source="portfolio_snapshot",
        source_id=s.id,
        target_date=str(td),
        title=f"{pname} · {mlabel} {s.year}",
        body=notes,
        context_label=f"Portfolio · {pname} · {mlabel} {s.year}",
        context_href=f"/portfolios/{s.portfolio_id}",
        created_at=_iso_dt(s.created_at),
        updated_at=None,
        can_edit_date=False,
        can_delete=False,
    )


def _hub_item_from_arbitrage(o: ArbitrageOperation) -> JournalHubItem:
    notes = (o.notes or "").strip()
    td = o.created_at.date() if o.created_at else date.today()
    return JournalHubItem(
        key=f"arbitrage_operation:{o.id}",
        source="arbitrage_operation",
        source_id=o.id,
        target_date=str(td),
        title=f"{o.pair} · {o.buy_source}→{o.sell_source}",
        body=notes,
        context_label=f"Arbitraje · {o.pair}",
        context_href="/arbitrage",
        created_at=_iso_dt(o.created_at),
        updated_at=None,
        can_edit_date=False,
        can_delete=False,
    )


def _hub_item_from_journal(e: JournalEntry) -> JournalHubItem:
    title = (e.title or "").strip() or None
    return JournalHubItem(
        key=f"journal:{e.id}",
        source="journal",
        source_id=e.id,
        target_date=str(e.target_date),
        title=title,
        body=e.body or "",
        context_label="Bitácora",
        context_href="/journal",
        created_at=_iso_dt(e.created_at),
        updated_at=_iso_dt(e.updated_at) or None,
        can_edit_date=True,
        can_delete=True,
    )


def _collect_hub_items(db: Session) -> list[JournalHubItem]:
    items: list[JournalHubItem] = []

    for r in db.query(DividendCalendarNote).order_by(DividendCalendarNote.note_date.desc()).all():
        if (r.body or "").strip():
            items.append(_hub_item_from_dividend_note(r))

    for m in db.query(ManualCalendarDividend).order_by(ManualCalendarDividend.div_date.desc()).all():
        if (m.note or "").strip():
            items.append(_hub_item_from_manual(m))

    snaps = (
        db.query(PortfolioSnapshot, Portfolio)
        .outerjoin(Portfolio, PortfolioSnapshot.portfolio_id == Portfolio.id)
        .order_by(PortfolioSnapshot.year.desc(), PortfolioSnapshot.month.desc())
        .all()
    )
    for snap, pf in snaps:
        if (snap.notes or "").strip():
            items.append(_hub_item_from_snapshot(snap, pf))

    for o in db.query(ArbitrageOperation).order_by(ArbitrageOperation.created_at.desc()).all():
        if (o.notes or "").strip():
            items.append(_hub_item_from_arbitrage(o))

    for e in db.query(JournalEntry).order_by(JournalEntry.target_date.desc()).all():
        if (e.body or "").strip():
            items.append(_hub_item_from_journal(e))

    return items


@router.get("/hub", response_model=list[JournalHubItem])
def journal_hub(
    source: Optional[JournalSource] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    sort: str = Query("target_date_desc", description="target_date_desc | target_date_asc"),
    db: Session = Depends(get_db),
):
    items = _collect_hub_items(db)

    if source:
        items = [i for i in items if i.source == source]

    if start_date or end_date:
        start_dt = _parse_date_param(start_date, date(1970, 1, 1))
        end_dt = _parse_date_param(end_date, date(2099, 12, 31))
        if end_dt < start_dt:
            start_dt, end_dt = end_dt, start_dt
        filtered = []
        for i in items:
            try:
                td = datetime.strptime(i.target_date[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
            if start_dt <= td <= end_dt:
                filtered.append(i)
        items = filtered

    if search and search.strip():
        q = search.strip().lower()
        items = [
            i
            for i in items
            if q in i.body.lower()
            or (i.title and q in i.title.lower())
            or q in i.context_label.lower()
        ]

    reverse = sort != "target_date_asc"
    items.sort(key=lambda i: (i.target_date, i.key), reverse=reverse)
    return items


@router.post("/entries", response_model=JournalHubItem)
def create_journal_entry(body: JournalEntryCreate, db: Session = Depends(get_db)):
    text = (body.body or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="El texto de la nota no puede estar vacío.")
    td = _parse_date_param(body.target_date, date.today())
    row = JournalEntry(
        title=(body.title or "").strip(),
        body=text,
        target_date=td,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _hub_item_from_journal(row)


@router.patch("/entries/{entry_id}", response_model=JournalHubItem)
def patch_journal_entry(entry_id: int, body: JournalEntryPatch, db: Session = Depends(get_db)):
    row = db.query(JournalEntry).filter_by(id=entry_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Nota no encontrada")
    if body.title is not None:
        row.title = body.title.strip()
    if body.body is not None:
        text = body.body.strip()
        if not text:
            raise HTTPException(status_code=400, detail="El texto de la nota no puede estar vacío.")
        row.body = text
    if body.target_date is not None:
        row.target_date = _parse_date_param(body.target_date, row.target_date)
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _hub_item_from_journal(row)


@router.delete("/entries/{entry_id}")
def delete_journal_entry(entry_id: int, db: Session = Depends(get_db)):
    row = db.query(JournalEntry).filter_by(id=entry_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Nota no encontrada")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.patch("/dividend-calendar/{note_id}", response_model=JournalHubItem)
def patch_dividend_calendar_note(note_id: int, body: DividendCalendarNotePatch, db: Session = Depends(get_db)):
    row = db.query(DividendCalendarNote).filter_by(id=note_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Nota no encontrada")
    if body.note_date is not None:
        row.note_date = _parse_date_param(body.note_date, row.note_date)
    if body.title is not None:
        row.title = body.title.strip()
    if body.body is not None:
        text = body.body.strip()
        if not text:
            raise HTTPException(status_code=400, detail="El texto de la nota no puede estar vacío.")
        row.body = text
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _hub_item_from_dividend_note(row)


@router.delete("/dividend-calendar/{note_id}")
def delete_dividend_calendar_note(note_id: int, db: Session = Depends(get_db)):
    row = db.query(DividendCalendarNote).filter_by(id=note_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Nota no encontrada")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.patch("/manual-dividend/{entry_id}", response_model=JournalHubItem)
def patch_manual_dividend_note(entry_id: int, body: NoteBodyPatch, db: Session = Depends(get_db)):
    row = db.query(ManualCalendarDividend).filter_by(id=entry_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Entrada manual no encontrada")
    text = body.body.strip()
    if not text:
        raise HTTPException(status_code=400, detail="El texto de la nota no puede estar vacío.")
    row.note = text
    db.commit()
    db.refresh(row)
    return _hub_item_from_manual(row)


@router.patch("/portfolio-snapshot/{snapshot_id}", response_model=JournalHubItem)
def patch_portfolio_snapshot_note(snapshot_id: int, body: NoteBodyPatch, db: Session = Depends(get_db)):
    snap = db.query(PortfolioSnapshot).filter_by(id=snapshot_id).first()
    if not snap:
        raise HTTPException(status_code=404, detail="Snapshot no encontrado")
    text = body.body.strip()
    if not text:
        raise HTTPException(status_code=400, detail="El texto de la nota no puede estar vacío.")
    snap.notes = text
    db.commit()
    pf = db.query(Portfolio).filter_by(id=snap.portfolio_id).first()
    return _hub_item_from_snapshot(snap, pf)


@router.patch("/arbitrage-operation/{operation_id}", response_model=JournalHubItem)
def patch_arbitrage_operation_note(operation_id: int, body: NoteBodyPatch, db: Session = Depends(get_db)):
    op = db.query(ArbitrageOperation).filter_by(id=operation_id).first()
    if not op:
        raise HTTPException(status_code=404, detail="Operación no encontrada")
    text = body.body.strip()
    if not text:
        raise HTTPException(status_code=400, detail="El texto de la nota no puede estar vacío.")
    op.notes = text
    db.commit()
    db.refresh(op)
    return _hub_item_from_arbitrage(op)
