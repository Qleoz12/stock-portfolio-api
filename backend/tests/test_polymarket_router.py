"""Tests for Polymarket market normalization (mock data, no live API)."""
import unittest

from routers.polymarket import normalize_polymarket_market


class TestPolymarketNormalize(unittest.TestCase):
    def test_normalize_with_outcome_prices(self):
        raw = {
            "question": "Will HOOD reach $90 in July 2026?",
            "slug": "hood-90-july",
            "outcomePrices": '["0.58", "0.42"]',
            "bestBid": 0.57,
            "bestAsk": 0.59,
            "volumeNum": 12000,
            "liquidityNum": 5000,
            "endDate": "2026-08-01T00:00:00Z",
        }
        row = normalize_polymarket_market(raw, symbol_hint="HOOD", spot=99.96)
        self.assertEqual(row["source"], "polymarket")
        self.assertEqual(row["yes_implied_pct"], 58.0)
        self.assertEqual(row["strike_price"], 90.0)
        self.assertTrue(row["is_price_market"])
        self.assertIn("polymarket.com", row["url"])

    def test_normalize_list_outcome_prices(self):
        raw = {
            "question": "HOOD above $130",
            "slug": "hood-130",
            "outcomePrices": [0.05, 0.95],
            "endDate": "2026-08-01",
        }
        row = normalize_polymarket_market(raw, symbol_hint="HOOD", spot=100.0)
        self.assertEqual(row["yes_implied_pct"], 5.0)
        self.assertEqual(row["direction"], "touch_above")


if __name__ == "__main__":
    unittest.main()
