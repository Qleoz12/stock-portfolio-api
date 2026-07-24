import unittest
from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import DividendForwardEvent, ManualCalendarDividend, Stock
from services.dividend_capture import _pick_best_candidate, next_dividend_capture


class TestDividendCapture(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.stock = Stock(ticker_yf="TEST", symbol="TEST", company_name="Test Co")
        self.db.add(self.stock)
        self.db.commit()
        self.db.refresh(self.stock)
        self.today = date(2026, 6, 15)

    def tearDown(self):
        self.db.close()

    def test_no_future_events_returns_empty(self):
        out = next_dividend_capture(self.db, self.stock.id, 100.0, as_of=self.today)
        self.assertIsNone(out["next_ex_date"])
        self.assertIsNone(out["days_to_next_ex"])
        self.assertIsNone(out["exp_div_apy_pct"])

    def test_forward_event_10_days(self):
        ex = self.today + timedelta(days=10)
        self.db.add(
            DividendForwardEvent(
                stock_id=self.stock.id,
                div_date=ex,
                div_amount=0.5,
                projection_source="yahoo_ex",
            )
        )
        self.db.commit()
        out = next_dividend_capture(self.db, self.stock.id, 50.0, as_of=self.today)
        self.assertEqual(out["next_ex_date"], str(ex))
        self.assertEqual(out["days_to_next_ex"], 10)
        self.assertEqual(out["next_div_source"], "yahoo_ex")
        # (0.5/50) * (365/10) * 100 = 36.5
        self.assertEqual(out["exp_div_apy_pct"], 36.5)

    def test_forward_event_5_days(self):
        ex = self.today + timedelta(days=5)
        self.db.add(
            DividendForwardEvent(
                stock_id=self.stock.id,
                div_date=ex,
                div_amount=1.0,
                projection_source="yahoo_ex",
            )
        )
        self.db.commit()
        out = next_dividend_capture(self.db, self.stock.id, 100.0, as_of=self.today)
        self.assertEqual(out["days_to_next_ex"], 5)
        # (1/100) * (365/5) * 100 = 73.0
        self.assertEqual(out["exp_div_apy_pct"], 73.0)

    def test_prefers_yahoo_ex_over_seasonal_same_date(self):
        ex = self.today + timedelta(days=8)
        picked = _pick_best_candidate([
            (ex, 0.25, "seasonal_1y"),
            (ex, 0.30, "yahoo_ex"),
        ])
        self.assertIsNotNone(picked)
        assert picked is not None
        self.assertEqual(picked[2], "yahoo_ex")
        self.assertEqual(picked[1], 0.30)

    def test_earliest_date_wins_across_sources(self):
        sooner = self.today + timedelta(days=6)
        later = self.today + timedelta(days=20)
        self.db.add(
            DividendForwardEvent(
                stock_id=self.stock.id,
                div_date=later,
                div_amount=0.5,
                projection_source="yahoo_ex",
            )
        )
        self.db.add(
            ManualCalendarDividend(
                stock_id=self.stock.id,
                div_date=sooner,
                ticker_yf="TEST",
                div_amount=0.4,
            )
        )
        self.db.commit()
        out = next_dividend_capture(self.db, self.stock.id, 50.0, as_of=self.today)
        self.assertEqual(out["next_ex_date"], str(sooner))
        self.assertEqual(out["next_div_source"], "manual")
        self.assertEqual(out["days_to_next_ex"], 6)

    def test_ex_date_today_zero_days(self):
        self.db.add(
            DividendForwardEvent(
                stock_id=self.stock.id,
                div_date=self.today,
                div_amount=0.25,
                projection_source="yahoo_ex",
            )
        )
        self.db.commit()
        out = next_dividend_capture(self.db, self.stock.id, 25.0, as_of=self.today)
        self.assertEqual(out["days_to_next_ex"], 0)
        # max(days,1) => uses 1 day for APY
        self.assertEqual(out["exp_div_apy_pct"], 365.0)


if __name__ == "__main__":
    unittest.main()
