"""Export service for clustering results and datasets."""
from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime
from typing import Any, Optional

import pandas as pd
from sqlalchemy.orm import Session

from analytics.export.bundle_builder import build_zip_bundle, try_execute_notebook
from analytics.export.notebook_exporter import build_notebook, notebook_to_bytes, validate_notebook_syntax
from analytics.services.clustering_service import RUNS_DIR, ClusteringService
from analytics.services.dataset_service import DatasetService
from analytics.utils.json_safe import sanitize_for_json

RUNS_DIR.mkdir(parents=True, exist_ok=True)


class ExportService:
    def __init__(self, clustering_service: ClusteringService, db: Session | None = None) -> None:
        self.cs = clustering_service
        self.db = db

    def _require_run(self, run_id: str):
        result = self.cs.get_run(run_id)
        data = self.cs.get_run_data(run_id)
        if not result:
            raise ValueError(f"Run {run_id} not found")
        return result, data

    def export_csv(self, run_id: str) -> bytes:
        result, _ = self._require_run(run_id)
        best = next(
            (a for a in result.algorithms if a.algorithm == result.best_algorithm),
            result.algorithms[0] if result.algorithms else None,
        )
        rows = []
        if best:
            for a in best.assignments:
                rows.append({"ticker": a.ticker, "cluster_id": a.cluster_id, "silhouette": a.silhouette})
        return pd.DataFrame(rows).to_csv(index=False).encode("utf-8")

    def export_dataset(
        self,
        universe_id: str,
        view: str = "raw",
        fmt: str = "csv",
        period_days: int = 365,
        feature_profile: str = "ALL_CLUSTERING_ELIGIBLE_FEATURES",
        features: list[str] | None = None,
    ) -> tuple[bytes, str]:
        if not self.db:
            raise ValueError("Database session required for dataset export")
        payload = DatasetService(self.db).get_dataset(
            universe_id, view, period_days, feature_profile, features,
        )
        df = pd.DataFrame(payload.get("rows", []))
        stem = f"dataset_{universe_id}_{view}"
        if fmt == "parquet":
            buf = io.BytesIO()
            df.to_parquet(buf, index=False)
            return buf.getvalue(), f"{stem}.parquet"
        if fmt == "xlsx":
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                df.to_excel(writer, sheet_name=view[:31], index=False)
            return buf.getvalue(), f"{stem}.xlsx"
        return df.to_csv(index=False).encode("utf-8"), f"{stem}.csv"

    def export_excel(self, run_id: str) -> bytes:
        result, data = self._require_run(run_id)
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            summary = pd.DataFrame([{
                "run_id": result.run_id,
                "universe": result.universe_id,
                "mode": result.mode.value if hasattr(result.mode, "value") else result.mode,
                "k_recommended": result.k_recommended,
                "hopkins": result.hopkins_statistic,
                "best_algorithm": result.best_algorithm,
                "created_at": str(result.created_at),
            }])
            summary.to_excel(writer, sheet_name="Summary", index=False)

            pd.DataFrame({"feature": result.features_used}).to_excel(writer, sheet_name="Feature Catalog", index=False)
            pd.DataFrame([result.lineage or {}]).to_excel(writer, sheet_name="Configuration", index=False)

            if "df_records" in data:
                pd.DataFrame(data["df_records"]).to_excel(writer, sheet_name="Raw Data", index=False)
            if "processed_records" in data:
                pd.DataFrame(data["processed_records"]).to_excel(writer, sheet_name="Scaled Features", index=False)

            if "optimal_k" in data:
                ok = data["optimal_k"]
                pd.DataFrame([{
                    "consensus_k": ok.get("consensus_k"),
                    "agreement_level": ok.get("agreement_level"),
                    "agreement_label": ok.get("agreement_label"),
                }]).to_excel(writer, sheet_name="Optimal K", index=False)

            if "algorithm_ranking" in data:
                pd.DataFrame(data["algorithm_ranking"]).to_excel(writer, sheet_name="Algorithm Comparison", index=False)

            best = next(
                (a for a in result.algorithms if a.algorithm == result.best_algorithm),
                result.algorithms[0] if result.algorithms else None,
            )
            if best:
                rows = [{"ticker": a.ticker, "cluster": a.cluster_id, "silhouette": a.silhouette} for a in best.assignments]
                pd.DataFrame(rows).to_excel(writer, sheet_name="Cluster Assignments", index=False)

            if "corr_matrix" in data and "tickers" in data:
                corr = pd.DataFrame(data["corr_matrix"], index=data["tickers"], columns=data["tickers"])
                corr.reset_index().to_excel(writer, sheet_name="Correlation Matrix", index=False)
            if "distance_matrix" in data and "tickers" in data:
                dist = pd.DataFrame(data["distance_matrix"], index=data["tickers"], columns=data["tickers"])
                dist.reset_index().to_excel(writer, sheet_name="Distance Matrix", index=False)

            metrics_rows = [
                {"algorithm": a.algorithm, **a.metrics, "negative_silhouette": a.negative_silhouette_count}
                for a in result.algorithms
            ]
            pd.DataFrame(metrics_rows).to_excel(writer, sheet_name="Validation Metrics", index=False)

        buf.seek(0)
        return buf.read()

    def export_notebook(self, run_id: str) -> bytes:
        result, data = self._require_run(run_id)
        nb = build_notebook(run_id, sanitize_for_json(result.model_dump()), sanitize_for_json(data))
        return notebook_to_bytes(nb)

    def export_json(self, run_id: str) -> bytes:
        result, data = self._require_run(run_id)
        payload = sanitize_for_json({"result": result.model_dump(), "data": data})
        return json.dumps(payload, indent=2).encode("utf-8")

    def export_parquet_features(self, run_id: str) -> bytes:
        _, data = self._require_run(run_id)
        key = "processed_records" if "processed_records" in data else "df_records"
        if key not in data:
            raise ValueError("No feature data for this run")
        buf = io.BytesIO()
        pd.DataFrame(data[key]).to_parquet(buf, index=False)
        buf.seek(0)
        return buf.read()

    def export_zip_bundle(self, run_id: str) -> bytes:
        result, data = self._require_run(run_id)
        return build_zip_bundle(run_id, sanitize_for_json(result.model_dump()), sanitize_for_json(data))

    def export_full_bundle(self, run_id: str) -> tuple[bytes, dict[str, Any]]:
        """Build ZIP with optional executed notebook; returns (bytes, status_meta)."""
        result, data = self._require_run(run_id)
        safe_result = sanitize_for_json(result.model_dump())
        safe_data = sanitize_for_json(data)

        status: dict[str, Any] = {
            "run_id": run_id,
            "notebook_source": "ready",
            "notebook_executed": "not_generated",
            "html": "not_generated",
            "error": None,
            "exported_at": datetime.utcnow().isoformat(),
        }

        zip_bytes = build_zip_bundle(run_id, safe_result, safe_data)

        executed, err = try_execute_notebook(run_id, safe_result, safe_data)
        if executed:
            status["notebook_executed"] = "ready"
        elif err:
            status["notebook_executed"] = "failed"
            status["error"] = err

        return zip_bytes, status

    def validate_notebook_cells(self, run_id: str) -> list[str]:
        result, data = self._require_run(run_id)
        nb = build_notebook(run_id, sanitize_for_json(result.model_dump()), sanitize_for_json(data))
        return validate_notebook_syntax(nb)
