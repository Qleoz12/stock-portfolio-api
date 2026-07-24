import unittest
from datetime import date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import (
    ArbitrageOperation,
    DividendCalendarNote,
    Exchange,
    JournalEntry,
    ManualCalendarDividend,
    Portfolio,
    PortfolioSnapshot,
    Stock,
)
from routers.journal import _collect_hub_items, patch_dividend_calendar_note, patch_journal_entry
from routers.journal import JournalEntryPatch, DividendCalendarNotePatch


class TestJournalHub(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

        exc = Exchange(name="New York", code="NYSE")
        self.db.add(exc)
        self.db.flush()

        pf = Portfolio(name="Test PF", broker="IB")
        self.db.add(pf)
        self.db.flush()

        self.db.add(
            DividendCalendarNote(
                note_date=date(2026, 7, 10),
                body="Revisar ex-dates",
                title="Div check",
            )
        )
        self.db.add(
            ManualCalendarDividend(
                div_date=date(2026, 7, 5),
                ticker_yf="AAPL",
                div_amount=0.25,
                note="Ex-div según anuncio",
            )
        )
        self.db.add(
            ManualCalendarDividend(
                div_date=date(2026, 7, 6),
                ticker_yf="MSFT",
                div_amount=0.75,
                note="",
            )
        )
        self.db.add(
            PortfolioSnapshot(
                portfolio_id=pf.id,
                month=6,
                year=2026,
                total_value=10000,
                total_dividends=200,
                notes="Junio fuerte en yield",
            )
        )
        self.db.add(
            PortfolioSnapshot(
                portfolio_id=pf.id,
                month=5,
                year=2026,
                total_value=9000,
                total_dividends=150,
                notes="",
            )
        )
        self.db.add(
            ArbitrageOperation(
                pair="USDT/COP",
                buy_source="binance",
                sell_source="okx",
                buy_price=4000,
                sell_price=4050,
                amount_usdt=100,
                notes="Spread interesante",
            )
        )
        self.db.add(
            ArbitrageOperation(
                pair="USDT/COP",
                buy_source="a",
                sell_source="b",
                buy_price=4000,
                sell_price=4010,
                amount_usdt=50,
                notes="",
            )
        )
        self.db.add(
            JournalEntry(
                target_date=date(2026, 8, 1),
                title="Meta Q3",
                body="Rebalancear tech",
            )
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_collect_excludes_empty_notes(self):
        items = _collect_hub_items(self.db)
        sources = {i.source for i in items}
        self.assertIn("dividend_calendar", sources)
        self.assertIn("manual_dividend", sources)
        self.assertIn("portfolio_snapshot", sources)
        self.assertIn("arbitrage_operation", sources)
        self.assertIn("journal", sources)
        self.assertEqual(len(items), 5)
        manual = [i for i in items if i.source == "manual_dividend"]
        self.assertEqual(len(manual), 1)
        self.assertEqual(manual[0].body, "Ex-div según anuncio")

    def test_sorted_by_target_date_desc(self):
        items = _collect_hub_items(self.db)
        items.sort(key=lambda i: (i.target_date, i.key), reverse=True)
        dates = [i.target_date for i in items]
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_patch_journal_entry(self):
        entry = self.db.query(JournalEntry).first()
        updated = patch_journal_entry(
            entry.id,
            JournalEntryPatch(body="Texto actualizado", target_date="2026-09-01"),
            self.db,
        )
        self.assertEqual(updated.body, "Texto actualizado")
        self.assertEqual(updated.target_date, "2026-09-01")

    def test_patch_dividend_calendar_note(self):
        note = self.db.query(DividendCalendarNote).first()
        updated = patch_dividend_calendar_note(
            note.id,
            DividendCalendarNotePatch(note_date="2026-07-15", body="Nuevo texto"),
            self.db,
        )
        self.assertEqual(updated.target_date, "2026-07-15")
        self.assertEqual(updated.body, "Nuevo texto")


if __name__ == "__main__":
    unittest.main()
