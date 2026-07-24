import unittest
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import Exchange, Stock, StockFeature
from routers.stocks import _stocks_list_base_query


class TestStocksScreener(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

        exc = Exchange(name="New York", code="NYSE")
        self.db.add(exc)
        self.db.flush()

        self.stock_a = Stock(
            ticker_yf="GOOD", symbol="GOOD", company_name="Good Co", exchange_id=exc.id
        )
        self.stock_b = Stock(
            ticker_yf="WEAK", symbol="WEAK", company_name="Weak Co", exchange_id=exc.id
        )
        self.stock_c = Stock(
            ticker_yf="FLAT", symbol="FLAT", company_name="Flat Co", exchange_id=exc.id
        )
        self.db.add_all([self.stock_a, self.stock_b, self.stock_c])
        self.db.flush()

        self.db.add_all(
            [
                StockFeature(
                    stock_id=self.stock_a.id,
                    last_close=90.0,
                    ema_52=100.0,
                    ema_200=110.0,
                    health_score=65.0,
                    day_change_pct=-5.0,
                    updated_at=datetime.utcnow(),
                ),
                StockFeature(
                    stock_id=self.stock_b.id,
                    last_close=80.0,
                    ema_52=95.0,
                    ema_200=105.0,
                    health_score=40.0,
                    day_change_pct=-6.0,
                    updated_at=datetime.utcnow(),
                ),
                StockFeature(
                    stock_id=self.stock_c.id,
                    last_close=120.0,
                    ema_52=100.0,
                    ema_200=110.0,
                    health_score=80.0,
                    day_change_pct=-4.0,
                    updated_at=datetime.utcnow(),
                ),
            ]
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def _ids(self, **kwargs):
        q = _stocks_list_base_query(self.db, for_list=False, **kwargs)
        return {r.id for r in q.with_entities(Stock.id).all()}

    def test_below_selected_emas_allows_score_50(self):
        ids = self._ids(
            min_health_score=50,
            divergence="below_selected_emas",
            ema_52_for_div=True,
            ema_200_for_div=True,
        )
        self.assertIn(self.stock_a.id, ids)
        self.assertNotIn(self.stock_b.id, ids)
        self.assertNotIn(self.stock_c.id, ids)

    def test_strong_below_selected_still_requires_70(self):
        ids = self._ids(
            min_health_score=50,
            divergence="strong_below_selected",
            ema_52_for_div=True,
            ema_200_for_div=True,
        )
        self.assertNotIn(self.stock_a.id, ids)

    def test_day_change_pct_band(self):
        ids = self._ids(min_day_change_pct=-10, max_day_change_pct=-3.3)
        self.assertEqual(ids, {self.stock_a.id, self.stock_b.id, self.stock_c.id})

        ids = self._ids(min_day_change_pct=-5.5, max_day_change_pct=-4.5)
        self.assertEqual(ids, {self.stock_a.id})

    def test_finviz_style_combined_preset(self):
        ids = self._ids(
            min_health_score=50,
            max_health_score=100,
            min_day_change_pct=-10,
            max_day_change_pct=-3.3,
            divergence="below_selected_emas",
            ema_52_for_div=True,
            ema_200_for_div=True,
            tech_complete=True,
        )
        self.assertEqual(ids, {self.stock_a.id})

    def test_exclude_value_traps(self):
        self.stock_a.possible_value_trap = True
        self.db.commit()
        ids_all = self._ids()
        ids_excluded = self._ids(exclude_value_traps=True)
        self.assertIn(self.stock_a.id, ids_all)
        self.assertNotIn(self.stock_a.id, ids_excluded)
        self.assertIn(self.stock_b.id, ids_excluded)
        self.assertIn(self.stock_c.id, ids_excluded)


if __name__ == "__main__":
    unittest.main()
