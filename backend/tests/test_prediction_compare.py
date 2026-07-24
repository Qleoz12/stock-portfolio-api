"""Tests for prediction_compare date coercion."""
import unittest
from datetime import date

from routers.prediction_compare import _coerce_date, _enrich_market_row


class TestPredictionCompareDates(unittest.TestCase):
    def test_coerce_date_from_string(self):
        self.assertEqual(_coerce_date("2026-07-29"), date(2026, 7, 29))

    def test_enrich_earnings_risk_with_string_earnings(self):
        row = _enrich_market_row(
            {
                "strike_price": 90.0,
                "direction": "touch_below",
                "end_date": "2026-08-01T00:00:00Z",
                "yes_ask": 0.58,
            },
            spot=100.0,
            annual_vol=0.8,
            user_prob=None,
            stake=50.0,
            earnings_date=date(2026, 7, 29),
        )
        self.assertTrue(row["earnings_risk"])


if __name__ == "__main__":
    unittest.main()
