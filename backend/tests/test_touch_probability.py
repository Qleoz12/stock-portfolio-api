"""Tests for touch_probability helpers."""
import unittest

from services.touch_probability import (
    bet_ev,
    move_pct,
    period_volatility,
    touch_probability,
    z_score,
)


class TestTouchProbability(unittest.TestCase):
    def test_move_pct(self):
        self.assertAlmostEqual(move_pct(100.0, 90.0), -10.0)
        self.assertAlmostEqual(move_pct(99.96, 130.0), 30.04, places=1)

    def test_period_vol(self):
        v = period_volatility(0.80, 10)
        self.assertIsNotNone(v)
        self.assertGreater(v, 0.1)
        self.assertLess(v, 0.2)

    def test_z_score(self):
        sig = period_volatility(0.80, 10)
        z = z_score(99.96, 90.0, sig)
        self.assertIsNotNone(z)
        self.assertLess(z, 0)

    def test_touch_below_more_likely_than_far_above(self):
        vol = 0.80
        days = 10
        spot = 100.0
        p90 = touch_probability(spot, 90.0, vol, days, "touch_below")
        p130 = touch_probability(spot, 130.0, vol, days, "touch_above")
        self.assertIsNotNone(p90)
        self.assertIsNotNone(p130)
        self.assertGreater(p90, p130)

    def test_bet_ev_positive_when_user_above_breakeven(self):
        # Yes at 58¢, user believes 65%
        ev = bet_ev(0.58, stake=50.0, user_prob=0.65, market_prob=0.58)
        self.assertEqual(ev.breakeven_prob, 0.58)
        self.assertIsNotNone(ev.ev_at_user_prob)
        self.assertGreater(ev.ev_at_user_prob, 0)

    def test_bet_ev_negative_when_user_below_breakeven(self):
        ev = bet_ev(0.58, stake=50.0, user_prob=0.50, market_prob=0.58)
        self.assertIsNotNone(ev.ev_at_user_prob)
        self.assertLess(ev.ev_at_user_prob, 0)


if __name__ == "__main__":
    unittest.main()
