"""Unit tests for Market Cluster Explorer analytics."""
from __future__ import annotations

import sys
import os
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


class TestFeatureDiscovery:
    def test_discover_all_returns_features(self):
        from analytics.features.discovery import discover_all
        features = discover_all()
        assert len(features) >= 20
        names = {f.name for f in features}
        assert "max_drawdown" in names
        assert "rsi_14" in names
        assert "annualized_return" in names

    def test_registry_profiles(self):
        from analytics.features.registry import get_registry
        reg = get_registry()
        profile = reg.get_profile("CORE_RISK_RETURN")
        assert profile is not None
        assert "max_drawdown" in profile.feature_names


class TestValidation:
    def test_validate_empty_dataset(self):
        from analytics.validation.quality_report import validate_dataset
        report = validate_dataset(pd.DataFrame(), dataset_id="test")
        assert report.status.value == "insufficient_data"

    def test_validate_good_dataset(self):
        from analytics.validation.quality_report import validate_dataset
        rng = np.random.default_rng(42)
        df = pd.DataFrame(rng.normal(size=(30, 5)), columns=list("abcde"))
        report = validate_dataset(df, dataset_id="test", min_assets=5)
        assert report.status.value in ("valid", "valid_with_warnings")
        assert report.asset_count == 30


class TestPreprocessing:
    def test_preprocess_features(self):
        from analytics.preprocessing.pipeline import preprocess_features
        rng = np.random.default_rng(0)
        df = pd.DataFrame(
            rng.normal(size=(20, 4)),
            columns=["a", "b", "c", "d"],
            index=[f"T{i}" for i in range(20)],
        )
        result = preprocess_features(df, ["a", "b", "c", "d"])
        assert result.X.shape == (20, 4)
        assert len(result.transformations) >= 2


class TestClusteringTendency:
    def test_hopkins_clusterable_data(self):
        from analytics.clustering.tendency import hopkins_statistic, interpret_hopkins
        rng = np.random.default_rng(42)
        X = np.vstack([rng.normal(0, 1, (50, 3)), rng.normal(5, 1, (50, 3))])
        h = hopkins_statistic(X)
        assert 0 <= h <= 1
        assert "cluster" in interpret_hopkins(h).lower() or "random" in interpret_hopkins(h).lower()

    def test_vat_ordering(self):
        from analytics.clustering.tendency import vat_ordering
        from scipy.spatial.distance import pdist, squareform
        rng = np.random.default_rng(0)
        X = rng.normal(size=(10, 3))
        D = squareform(pdist(X))
        reordered, order = vat_ordering(D)
        assert reordered.shape == (10, 10)
        assert len(order) == 10


class TestOptimalK:
    def test_find_optimal_k(self):
        from analytics.clustering.optimal_k import find_optimal_k
        rng = np.random.default_rng(42)
        X = np.vstack([rng.normal(0, 1, (40, 3)), rng.normal(4, 1, (40, 3))])
        result = find_optimal_k(X, k_min=2, k_max=6)
        assert result.consensus_k >= 2
        assert len(result.recommendations) >= 3


class TestClusteringAlgorithms:
    def test_hierarchical_and_kmeans(self):
        from analytics.clustering.algorithms import run_all_algorithms
        from analytics.clustering.validation import validate_clusters
        rng = np.random.default_rng(42)
        X = np.vstack([rng.normal(0, 1, (30, 4)), rng.normal(3, 1, (30, 4))])
        results = run_all_algorithms(X, k=2)
        assert len(results) >= 2
        metrics = validate_clusters(X, results[0].labels)
        assert -1 <= metrics.average_silhouette <= 1


class TestReturnsMatrix:
    def test_correlation_distance(self):
        from analytics.data.returns_matrix import correlation_matrix, distance_from_correlation
        rng = np.random.default_rng(0)
        df = pd.DataFrame(rng.normal(size=(100, 5)), columns=list("ABCDE"))
        corr = correlation_matrix(df)
        dist = distance_from_correlation(corr)
        assert dist.shape == (5, 5)
        assert np.allclose(np.diag(dist.values), 0)


class TestCalculators:
    def test_annualized_return(self):
        from analytics.features.calculators import annualized_return, volatility_1y
        r = pd.Series([0.01, -0.005, 0.008, 0.002] * 60)
        ar = annualized_return(r)
        vol = volatility_1y(r)
        assert ar is not None
        assert vol is not None
        assert vol > 0


class TestJsonSafe:
    def test_sanitize_nan_inf(self):
        import json
        from analytics.utils.json_safe import sanitize_for_json

        data = {"a": float("nan"), "b": float("inf"), "c": 0.123456789}
        clean = sanitize_for_json(data)
        json.dumps(clean)
        assert clean["a"] is None
        assert clean["b"] is None
        assert clean["c"] == 0.123457

    def test_sanitize_nested_df_records(self):
        import json
        from analytics.utils.json_safe import sanitize_for_json

        records = [
            {"ticker": "AAPL", "div_yield": float("nan"), "rsi": 45.123456789},
            {"ticker": "MSFT", "div_yield": 1.2, "rsi": float("inf")},
        ]
        payload = {"charts": {"df_records": records, "pca_coords": [[float("nan"), 1.0]]}}
        clean = sanitize_for_json(payload)
        json.dumps(clean)
        assert clean["charts"]["df_records"][0]["div_yield"] is None
        assert clean["charts"]["df_records"][1]["rsi"] is None
        assert clean["charts"]["pca_coords"][0][0] is None

    def test_get_run_data_serializable(self):
        import json
        from analytics.services import clustering_service as cs_mod
        from analytics.utils.json_safe import sanitize_for_json

        run_id = "test_nan_run"
        cs_mod._RUN_DATA[run_id] = {
            "df_records": [{"ticker": "X", "value": float("nan")}],
            "optimal_k": {"gap": {2: float("nan"), 3: 0.5}},
        }
        try:
            data = sanitize_for_json(cs_mod._RUN_DATA[run_id])
            json.dumps(data)
            assert data["df_records"][0]["value"] is None
            assert data["optimal_k"]["gap"]["2"] is None or data["optimal_k"]["gap"][2] is None
        finally:
            cs_mod._RUN_DATA.pop(run_id, None)
