from services.valuation_service import (
    _median_positive,
    _model_value_from_medians,
    _pearson_pct,
    build_quarter_metrics,
    verdict_from_ratio,
    _growth_rows,
)


def test_verdict_significantly_undervalued():
    code, label = verdict_from_ratio(0.49)
    assert code == "significantly_undervalued"
    assert "Significantly" in label


def test_verdict_modestly_undervalued():
    code, _ = verdict_from_ratio(0.85)
    assert code == "modestly_undervalued"


def test_verdict_fairly_valued():
    code, _ = verdict_from_ratio(1.0)
    assert code == "fairly_valued"


def test_verdict_overvalued():
    code, _ = verdict_from_ratio(1.35)
    assert code == "significantly_overvalued"


def test_median_positive():
    assert _median_positive([10, 20, None, 15]) == 15.0
    assert _median_positive([None, -1]) is None


def test_pearson_perfect():
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert _pearson_pct(x, x) == 100.0


def test_model_value_from_medians():
    mv = _model_value_from_medians(
        med_pe=20.0,
        med_ps=2.0,
        med_pb=3.0,
        med_pocf=15.0,
        eps_ttm=2.0,
        revenue_ps=10.0,
        book_ps=5.0,
        ocf_ps=4.0,
    )
    assert mv is not None
    assert 30 <= mv <= 50


def test_growth_rows():
    rows = _growth_rows(65.0, 130.0, 0.08)
    assert len(rows) == 4
    assert rows[0]["horizon"] == "current"
    assert rows[0]["ratio"] == 0.5
    assert rows[-1]["model_value"] > rows[0]["model_value"]
