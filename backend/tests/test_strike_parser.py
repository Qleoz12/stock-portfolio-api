"""Tests for strike_parser."""
import unittest

from services.strike_parser import parse_market_strike


class TestStrikeParser(unittest.TestCase):
    def test_hood_below_90(self):
        r = parse_market_strike(
            "Will HOOD fall to $90 or below in July 2026?",
            symbol_hint="HOOD",
            spot=99.96,
        )
        self.assertEqual(r.strike_price, 90.0)
        self.assertEqual(r.direction, "touch_below")
        self.assertTrue(r.is_price_market)
        self.assertEqual(r.ticker, "HOOD")

    def test_hood_above_130(self):
        r = parse_market_strike(
            "Robinhood (HOOD) above $130 during July?",
            symbol_hint="HOOD",
            spot=99.96,
        )
        self.assertEqual(r.strike_price, 130.0)
        self.assertEqual(r.direction, "touch_above")

    def test_arrow_down_price(self):
        r = parse_market_strike("↓ $90 — Yes", symbol_hint="HOOD", spot=100.0)
        self.assertEqual(r.strike_price, 90.0)
        self.assertEqual(r.direction, "touch_below")

    def test_infer_direction_from_spot(self):
        r = parse_market_strike("HOOD $85", symbol_hint="HOOD", spot=100.0)
        self.assertEqual(r.strike_price, 85.0)
        self.assertEqual(r.direction, "touch_below")

    def test_non_price_market(self):
        r = parse_market_strike("Will the Fed cut rates in July?")
        self.assertFalse(r.is_price_market)
        self.assertIsNone(r.strike_price)


if __name__ == "__main__":
    unittest.main()
