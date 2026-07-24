"""Main clustering orchestration service."""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
from scipy.spatial.distance import pdist, squareform
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_samples
from sqlalchemy.orm import Session

from analytics.clustering.algorithms import run_all_algorithms
from analytics.clustering.comparison import compare_algorithms_transparent
from analytics.clustering.correlation_pipeline import (
    CorrelationConfig,
    build_returns_matrix,
    correlation_distance_matrix,
)
from analytics.clustering.optimal_k import find_optimal_k
from analytics.clustering.tendency import hopkins_statistic, hopkins_status, vat_ordering
from analytics.clustering.validation import validate_clusters
from analytics.data.loaders import build_analytic_dataset, load_ohlcv_wide
from analytics.data.market_data_provider import MarketDataProvider
from analytics.data.returns_matrix import align_returns
from analytics.features.registry import get_registry
from analytics.features.transformations import apply_transformations
from analytics.models.clustering_result import (
    AlgorithmResult,
    AnalyzeRequest,
    ClusterAssignment,
    ClusteringMode,
    ClusteringRunResult,
)
from analytics.models.quality_report import DatasetLineage
from analytics.pipeline.cache import PipelineCache, STAGE_ORDER
from analytics.preprocessing.dimensionality import check_dimensionality
from analytics.preprocessing.pipeline import preprocess_features
from analytics.utils.json_safe import sanitize_for_json
from analytics.validation.quality_report import validate_dataset

RUNS_DIR = Path(__file__).resolve().parent.parent.parent / "analytics_runs"
_RUN_CACHE: dict[str, ClusteringRunResult] = {}
_RUN_DATA: dict[str, dict[str, Any]] = {}
_RUN_INDEX: list[dict[str, Any]] = []


class ClusteringService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.registry = get_registry()
        self.market_data = MarketDataProvider(db)

    def analyze(self, request: AnalyzeRequest, tickers: list[str]) -> ClusteringRunResult:
        run_id = str(uuid.uuid4())[:12]
        cache = PipelineCache(run_prefix=run_id)

        if request.mode == ClusteringMode.CORRELATION:
            return self._analyze_correlation(run_id, request, tickers, cache)

        return self._analyze_features(run_id, request, tickers, cache)

    def _analyze_features(
        self,
        run_id: str,
        request: AnalyzeRequest,
        tickers: list[str],
        cache: PipelineCache,
    ) -> ClusteringRunResult:
        raw_key = {"universe": request.universe_id, "period": request.period_days, "tickers": sorted(tickers)}
        cached_raw = cache.get("raw_data", raw_key)
        if cached_raw:
            df = pd.DataFrame(cached_raw["rows"]).set_index("ticker") if cached_raw.get("rows") else pd.DataFrame()
        else:
            df = build_analytic_dataset(self.db, tickers, request.period_days, request.benchmark)
            if not df.empty:
                df = apply_transformations(df)
                cache.set("raw_data", raw_key, {"rows": df.reset_index().to_dict(orient="records")})

        if df.empty:
            raise ValueError("No data available for selected tickers")

        available_tickers = list(df.index)
        if len(available_tickers) < 3:
            raise ValueError(f"Insufficient assets with data: {len(available_tickers)}")

        numeric_df = df.select_dtypes(include="number")
        quality = validate_dataset(numeric_df, dataset_id=request.universe_id)

        feature_cols = request.features
        if not feature_cols:
            feature_cols = self.registry.resolve_profile_features(
                request.feature_profile,
                available_columns=set(numeric_df.columns),
                df=numeric_df.loc[available_tickers],
            )

        if not feature_cols:
            raise ValueError("No valid features for clustering after quality filters")

        dim = check_dimensionality(len(available_tickers), len(feature_cols))

        feat_key = {**raw_key, "features": sorted(feature_cols)}
        cached_prep = cache.get("scaling", feat_key)
        if cached_prep:
            X = np.array(cached_prep["X"])
            tickers_used = cached_prep["tickers"]
            prep_meta = cached_prep["meta"]
        else:
            sub = numeric_df.loc[available_tickers, feature_cols]
            prep = preprocess_features(sub, feature_cols)
            X = prep.X
            tickers_used = prep.tickers
            prep_meta = {
                "transformations": prep.transformations,
                "rows_dropped": prep.rows_dropped,
                "values_imputed": prep.values_imputed,
                "scaler_name": prep.scaler_name,
            }
            cache.set("scaling", feat_key, {
                "X": X.tolist(), "tickers": tickers_used, "meta": prep_meta,
            })

        hopkins = hopkins_statistic(X, random_state=request.random_seed)
        hopkins_info = hopkins_status(hopkins)
        weak_structure = hopkins_info["state"] != "PASS"
        tendency_warning = None if hopkins_info["state"] == "PASS" else hopkins_info["meaning"]

        dist_matrix = squareform(pdist(X, metric="euclidean"))
        vat_matrix, vat_order = vat_ordering(dist_matrix)

        k_key = {**feat_key, "k_min": request.k_min, "k_max": request.k_max, "seed": request.random_seed}
        cached_k = cache.get("optimal_k", k_key)
        if cached_k:
            k = cached_k["consensus_k"]
            optimal = find_optimal_k(X, request.k_min, request.k_max, request.random_seed)
        else:
            optimal = find_optimal_k(X, request.k_min, request.k_max, request.random_seed)
            k = optimal.consensus_k
            cache.set("optimal_k", k_key, {"consensus_k": k})

        cluster_key = {**k_key, "k": k}
        cached_cluster = cache.get("clustering", cluster_key)
        if cached_cluster and cached_cluster.get("algo_outputs"):
            algo_outputs = run_all_algorithms(X, k, random_state=request.random_seed)
        else:
            algo_outputs = run_all_algorithms(X, k, random_state=request.random_seed)
            cache.set("clustering", cluster_key, {"k": k})

        algo_results, ranking_rows, best_algo, best_reason = self._build_algo_results(
            algo_outputs, X, tickers_used, k, weak_structure,
        )

        lineage = DatasetLineage(
            source="stock_unifier.db",
            variables_used=feature_cols,
            transformations=prep_meta.get("transformations", []),
            rows_removed=prep_meta.get("rows_dropped", 0),
            values_imputed=prep_meta.get("values_imputed", 0),
            normalization_method=prep_meta.get("scaler_name", "standard"),
            time_window=f"{request.period_days}d",
            benchmark=request.benchmark,
            random_seed=request.random_seed,
        )

        result = ClusteringRunResult(
            run_id=run_id,
            universe_id=request.universe_id,
            mode=request.mode,
            features_used=feature_cols,
            k_recommended=k,
            k_consensus=optimal.recommendations,
            hopkins_statistic=hopkins,
            tendency_warning=tendency_warning,
            algorithms=algo_results,
            best_algorithm=best_algo,
            best_algorithm_reason=best_reason,
            lineage=lineage.model_dump(),
            created_at=datetime.utcnow(),
        )

        pca = PCA(n_components=min(2, X.shape[1], X.shape[0]))
        pca_coords = pca.fit_transform(X)

        best_out = next((o for o in algo_outputs if self._algo_name(o) == best_algo), algo_outputs[0])
        sil_samples = silhouette_samples(X, best_out.labels) if len(set(best_out.labels)) > 1 else np.zeros(len(X))

        linkage_matrix = next(
            (o.linkage_matrix for o in algo_outputs if o.linkage_matrix is not None),
            None,
        )

        run_payload = {
            "tickers": tickers_used,
            "feature_cols": feature_cols,
            "X": X.tolist(),
            "pca_coords": pca_coords.tolist(),
            "pca_variance": pca.explained_variance_ratio_.tolist(),
            "labels": [int(best_out.labels[i]) for i in range(len(tickers_used))],
            "vat_matrix": vat_matrix.tolist(),
            "vat_order": vat_order.tolist(),
            "hopkins": hopkins_info,
            "dimensionality": asdict(dim),
            "optimal_k": {
                "elbow": optimal.elbow_inertia,
                "silhouette": optimal.silhouette_scores,
                "gap": optimal.gap_scores,
                "calinski": optimal.calinski_scores,
                "davies_bouldin": optimal.davies_bouldin_scores,
                "consensus_k": optimal.consensus_k,
                "recommendations": optimal.recommendations,
                "agreement_level": optimal.agreement_level,
                "agreement_label": optimal.agreement_label,
                "alternatives": optimal.alternatives or [],
            },
            "algorithm_ranking": [self._ranking_row_dict(r) for r in ranking_rows],
            "silhouette_samples": sil_samples.tolist(),
            "df_records": df.loc[tickers_used].reset_index().to_dict(orient="records"),
            "processed_records": pd.DataFrame(X, columns=feature_cols, index=tickers_used).reset_index().to_dict(orient="records"),
            "quality_status": quality.status.value,
            "linkage_matrix": linkage_matrix.tolist() if linkage_matrix is not None else None,
            "execution": {
                "data_source": "local_database",
                "yahoo_calls": self.market_data.external_requests,
                "cache_stages": STAGE_ORDER,
            },
        }
        self._store_run_data(run_id, result, run_payload)
        return result

    def _analyze_correlation(
        self,
        run_id: str,
        request: AnalyzeRequest,
        tickers: list[str],
        cache: PipelineCache,
    ) -> ClusteringRunResult:
        cfg = CorrelationConfig(
            frequency=request.correlation_frequency,
            method=request.correlation_method,
            lookback_days=request.period_days,
            min_observations=request.min_observations,
            distance_method=request.correlation_distance,
        )

        prices_df, _ = load_ohlcv_wide(self.db, tickers, request.period_days)
        returns_df = build_returns_matrix(prices_df, cfg.frequency)
        returns_df = align_returns(returns_df)
        if returns_df.shape[1] < 3:
            raise ValueError("Insufficient OHLCV data for correlation clustering")

        corr, dist, shared = correlation_distance_matrix(
            returns_df, cfg.method, cfg.distance_method,
        )
        tickers_used = list(corr.columns)
        X = dist.values

        quality = validate_dataset(returns_df.T, dataset_id=request.universe_id)

        hopkins = hopkins_statistic(X, random_state=request.random_seed)
        hopkins_info = hopkins_status(hopkins)
        weak_structure = True  # correlation mode is always exploratory for Hopkins

        vat_matrix, vat_order = vat_ordering(X)
        optimal = find_optimal_k(X, request.k_min, request.k_max, request.random_seed)
        k = optimal.consensus_k

        algo_outputs = run_all_algorithms(X, k, dist_matrix=X, random_state=request.random_seed)
        algo_results, ranking_rows, best_algo, best_reason = self._build_algo_results(
            algo_outputs, X, tickers_used, k, weak_structure,
        )

        result = ClusteringRunResult(
            run_id=run_id,
            universe_id=request.universe_id,
            mode=ClusteringMode.CORRELATION,
            features_used=["correlation_distance"],
            k_recommended=k,
            k_consensus=optimal.recommendations,
            hopkins_statistic=hopkins,
            tendency_warning=hopkins_info["meaning"],
            algorithms=algo_results,
            best_algorithm=best_algo,
            best_algorithm_reason=best_reason,
            created_at=datetime.utcnow(),
        )

        best_out = next((o for o in algo_outputs if self._algo_name(o) == best_algo), algo_outputs[0])
        linkage_matrix = next(
            (o.linkage_matrix for o in algo_outputs if o.linkage_matrix is not None),
            None,
        )

        run_payload = {
            "tickers": tickers_used,
            "corr_matrix": corr.values.tolist(),
            "distance_matrix": dist.values.tolist(),
            "shared_observations": shared.values.tolist(),
            "returns_records": returns_df.reset_index().to_dict(orient="records"),
            "labels": [int(best_out.labels[i]) for i in range(len(tickers_used))],
            "vat_matrix": vat_matrix.tolist(),
            "vat_order": vat_order.tolist(),
            "hopkins": hopkins_info,
            "correlation_config": {
                "frequency": cfg.frequency,
                "method": cfg.method,
                "distance_method": cfg.distance_method,
                "lookback_days": cfg.lookback_days,
            },
            "optimal_k": {
                "consensus_k": optimal.consensus_k,
                "recommendations": optimal.recommendations,
                "agreement_level": optimal.agreement_level,
                "agreement_label": optimal.agreement_label,
                "alternatives": optimal.alternatives or [],
                "silhouette": optimal.silhouette_scores,
                "gap": optimal.gap_scores,
                "elbow": optimal.elbow_inertia,
            },
            "algorithm_ranking": [self._ranking_row_dict(r) for r in ranking_rows],
            "quality_status": quality.status.value,
            "linkage_matrix": linkage_matrix.tolist() if linkage_matrix is not None else None,
            "execution": {
                "data_source": "local_database",
                "yahoo_calls": self.market_data.external_requests,
            },
        }
        self._store_run_data(run_id, result, run_payload)
        return result

    def _build_algo_results(
        self,
        algo_outputs: list,
        X: np.ndarray,
        tickers_used: list[str],
        k: int,
        weak_structure: bool,
    ) -> tuple[list[AlgorithmResult], list, str, str]:
        ranking_rows, best_algo, best_reason = compare_algorithms_transparent(
            algo_outputs, X, tickers_used, weak_structure=weak_structure,
        )
        algo_results: list[AlgorithmResult] = []
        seen: set[str] = set()

        for out in algo_outputs:
            name = self._algo_name(out)
            if name in seen:
                continue
            seen.add(name)

            if len(set(out.labels)) < 2:
                continue

            metrics_obj = validate_clusters(X, out.labels)
            assignments = [
                ClusterAssignment(
                    ticker=tickers_used[i],
                    cluster_id=int(out.labels[i]),
                    silhouette=metrics_obj.silhouette_per_obs[i],
                )
                for i in range(len(tickers_used))
            ]
            algo_results.append(
                AlgorithmResult(
                    algorithm=name,
                    linkage=out.linkage_method,
                    k=k,
                    assignments=assignments,
                    metrics={
                        "average_silhouette": metrics_obj.average_silhouette,
                        "dunn_index": metrics_obj.dunn_index,
                        "calinski_harabasz": metrics_obj.calinski_harabasz,
                        "davies_bouldin": metrics_obj.davies_bouldin,
                        "balance_score": metrics_obj.balance_score,
                    },
                    cluster_sizes=metrics_obj.cluster_sizes,
                    negative_silhouette_count=metrics_obj.negative_silhouette_count,
                )
            )

        return algo_results, ranking_rows, best_algo, best_reason

    @staticmethod
    def _algo_name(out) -> str:
        name = out.algorithm
        if out.linkage_method:
            name = f"hierarchical_{out.linkage_method}"
        return name

    @staticmethod
    def _ranking_row_dict(row) -> dict:
        return {
            "algorithm": row.algorithm,
            "linkage": row.linkage,
            "rank": row.rank,
            "composite_score": row.composite_score,
            "status": row.status,
            "raw_metrics": row.raw_metrics,
            "normalized_scores": row.normalized_scores,
            "weights": row.weights,
            "contributions": row.contributions,
        }

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        runs = list(_RUN_INDEX)
        if not runs and RUNS_DIR.exists():
            for p in sorted(RUNS_DIR.iterdir(), reverse=True)[:limit]:
                if p.is_dir() and (p / "result.json").exists():
                    data = json.loads((p / "result.json").read_text(encoding="utf-8"))
                    runs.append({
                        "run_id": data.get("run_id", p.name),
                        "universe_id": data.get("universe_id"),
                        "mode": data.get("mode"),
                        "created_at": data.get("created_at"),
                        "best_algorithm": data.get("best_algorithm"),
                        "k_recommended": data.get("k_recommended"),
                    })
        return runs[:limit]

    def get_run(self, run_id: str) -> Optional[ClusteringRunResult]:
        if run_id in _RUN_CACHE:
            return _RUN_CACHE[run_id]
        path = RUNS_DIR / run_id / "result.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return ClusteringRunResult(**data)
        return None

    def get_run_data(self, run_id: str) -> dict[str, Any]:
        if run_id in _RUN_DATA:
            return sanitize_for_json(_RUN_DATA[run_id])
        path = RUNS_DIR / run_id / "data.json"
        if path.exists():
            return sanitize_for_json(json.loads(path.read_text(encoding="utf-8")))
        return {}

    def _store_run_data(
        self,
        run_id: str,
        result: ClusteringRunResult,
        data: dict[str, Any],
    ) -> None:
        safe_data = sanitize_for_json(data)
        _RUN_CACHE[run_id] = result
        _RUN_DATA[run_id] = safe_data
        _RUN_INDEX.insert(0, {
            "run_id": run_id,
            "universe_id": result.universe_id,
            "mode": result.mode.value if hasattr(result.mode, "value") else result.mode,
            "created_at": result.created_at.isoformat(),
            "best_algorithm": result.best_algorithm,
            "k_recommended": result.k_recommended,
        })
        self._persist_run(run_id, result, safe_data)

    def _persist_run(self, run_id: str, result: ClusteringRunResult, data: dict) -> None:
        run_dir = RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        safe_result = sanitize_for_json(result.model_dump())
        (run_dir / "result.json").write_text(
            json.dumps(safe_result, indent=2), encoding="utf-8"
        )
        (run_dir / "data.json").write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )
