"""Tests for universe coverage."""
from __future__ import annotations

import sys
import os
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


class TestDimensionality:
    def test_recommended_max_for_25_assets(self):
        from analytics.preprocessing.dimensionality import check_dimensionality
        d = check_dimensionality(25, 39)
        assert d.recommended_max == 8
        assert d.is_high is True

    def test_ok_dimensionality(self):
        from analytics.preprocessing.dimensionality import check_dimensionality
        d = check_dimensionality(25, 5)
        assert d.is_high is False


class TestTransformations:
    def test_price_to_ema200(self):
        from analytics.features.transformations import apply_transformations
        df = pd.DataFrame({
            "last_close": [100.0, 200.0],
            "ema_200": [80.0, 100.0],
        }, index=["A", "B"])
        out = apply_transformations(df)
        assert "price_to_ema200" in out.columns
        assert abs(out.loc["A", "price_to_ema200"] - 0.25) < 0.01

    def test_raw_price_not_eligible(self):
        from analytics.features.transformations import is_clustering_eligible
        eligible, reason = is_clustering_eligible("ema_200")
        assert eligible is False
        assert "price" in reason.lower() or "ratio" in reason.lower()


class TestHopkinsStatus:
    def test_hopkins_states(self):
        from analytics.clustering.tendency import hopkins_status
        assert hopkins_status(0.8)["state"] == "PASS"
        assert hopkins_status(0.6)["state"] == "EXPLORATORY"
        assert hopkins_status(0.3)["state"] == "FAIL"


class TestComparison:
    def test_no_duplicate_algorithms(self):
        from analytics.clustering.algorithms import run_all_algorithms
        from analytics.clustering.comparison import compare_algorithms_transparent
        rng = np.random.default_rng(42)
        X = np.vstack([rng.normal(0, 1, (30, 4)), rng.normal(3, 1, (30, 4))])
        outputs = run_all_algorithms(X, k=2)
        rows, winner, _ = compare_algorithms_transparent(outputs, X, [f"T{i}" for i in range(60)])
        names = [r.algorithm for r in rows]
        assert len(names) == len(set(names))
        assert winner in names


class TestPipelineCache:
    def test_cache_get_set(self):
        from analytics.pipeline.cache import PipelineCache
        cache = PipelineCache(run_prefix="test")
        cache.set("universe", {"id": "dow30"}, {"tickers": ["A", "B"]})
        hit = cache.get("universe", {"id": "dow30"})
        assert hit is not None
        assert hit["tickers"] == ["A", "B"]


class TestCorrelationPipeline:
    def test_sqrt_half_distance(self):
        from analytics.clustering.correlation_pipeline import correlation_distance_matrix
        df = pd.DataFrame({"A": [0.01, -0.02, 0.03], "B": [0.02, -0.01, 0.02]})
        corr, dist, _ = correlation_distance_matrix(df, method="pearson", distance_method="sqrt_half")
        assert dist.shape == (2, 2)
        assert dist.loc["A", "A"] == 0.0


class TestNotebookExport:
    def test_build_notebook(self):
        from analytics.export.notebook_exporter import build_notebook, notebook_to_bytes
        result = {"universe_id": "dow30", "mode": "feature", "features_used": ["beta"], "k_recommended": 3,
                  "hopkins_statistic": 0.5, "k_consensus": {}, "best_algorithm": "kmeans",
                  "algorithms": [{"algorithm": "kmeans", "assignments": [{"ticker": "A", "cluster_id": 0}]}]}
        data = {"df_records": [{"ticker": "A"}], "algorithm_ranking": []}
        nb = build_notebook("abc123", result, data)
        assert nb["nbformat"] == 4
        assert len(nb["cells"]) >= 3
        assert len(notebook_to_bytes(nb)) > 100
