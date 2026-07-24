"""Build self-contained analyst ZIP bundles."""
from __future__ import annotations

import io
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd

from analytics.export.notebook_exporter import (
    build_notebook,
    get_readme,
    get_requirements_txt,
    notebook_to_bytes,
    validate_notebook_syntax,
)
from analytics.utils.json_safe import sanitize_for_json

EXPORTS_DIR = Path(__file__).resolve().parent.parent.parent / "analytics_exports"


def _df_or_empty(records: list | None) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)


def prepare_bundle_data(run_id: str, result: dict, data: dict) -> dict[str, bytes]:
    """Create all files for bundle as {relative_path: bytes}."""
    files: dict[str, bytes] = {}
    prefix = f"market_cluster_{run_id}"

    raw = _df_or_empty(data.get("df_records"))
    clean = _df_or_empty(data.get("processed_records") or data.get("df_records"))
    scaled = _df_or_empty(data.get("processed_records"))

    def to_parquet(df: pd.DataFrame) -> bytes:
        buf = io.BytesIO()
        df.to_parquet(buf, index=False)
        return buf.getvalue()

    def to_csv(df: pd.DataFrame) -> bytes:
        return df.to_csv(index=False).encode("utf-8")

    if not raw.empty:
        files[f"{prefix}/data/raw_dataset.parquet"] = to_parquet(raw)
    if not clean.empty:
        files[f"{prefix}/data/clean_dataset.parquet"] = to_parquet(clean)
    if not scaled.empty:
        files[f"{prefix}/data/scaled_features.parquet"] = to_parquet(scaled)

    # Returns
    returns = _df_or_empty(data.get("returns_records"))
    if not returns.empty:
        files[f"{prefix}/data/returns.parquet"] = to_parquet(returns)

    # Correlation / distance
    if "corr_matrix" in data and "tickers" in data:
        corr = pd.DataFrame(data["corr_matrix"], index=data["tickers"], columns=data["tickers"])
        files[f"{prefix}/data/correlation_matrix.csv"] = to_csv(corr.reset_index())
    if "distance_matrix" in data and "tickers" in data:
        dist = pd.DataFrame(data["distance_matrix"], index=data["tickers"], columns=data["tickers"])
        files[f"{prefix}/data/distance_matrix.csv"] = to_csv(dist.reset_index())

    # Assignments
    best = result.get("best_algorithm")
    assignments = []
    for algo in result.get("algorithms", []):
        if algo.get("algorithm") == best:
            assignments = algo.get("assignments", [])
            break
    if not assignments and result.get("algorithms"):
        assignments = result["algorithms"][0].get("assignments", [])
    if assignments:
        files[f"{prefix}/data/cluster_assignments.csv"] = to_csv(pd.DataFrame(assignments))

    # Ranking
    ranking = data.get("algorithm_ranking", [])
    if ranking:
        files[f"{prefix}/data/algorithm_ranking.csv"] = to_csv(pd.DataFrame(ranking))

    # Optimal K
    if "optimal_k" in data:
        files[f"{prefix}/data/optimal_k.json"] = json.dumps(
            sanitize_for_json(data["optimal_k"]), indent=2
        ).encode("utf-8")

    # Feature catalog
    features = result.get("features_used", [])
    if features:
        files[f"{prefix}/data/feature_catalog.csv"] = to_csv(
            pd.DataFrame({"feature": features, "selected": [True] * len(features)})
        )

    # Coverage placeholder
    files[f"{prefix}/data/universe_coverage.csv"] = to_csv(pd.DataFrame([{
        "universe_id": result.get("universe_id"),
        "mode": result.get("mode"),
    }]))

    files[f"{prefix}/data/validation_issues.csv"] = to_csv(pd.DataFrame(columns=["severity", "message"]))
    files[f"{prefix}/data/excluded_assets.csv"] = to_csv(pd.DataFrame(columns=["ticker", "reason"]))

    params = sanitize_for_json({
        "run_id": run_id,
        "universe_id": result.get("universe_id"),
        "mode": result.get("mode"),
        "features_used": result.get("features_used"),
        "k_recommended": result.get("k_recommended"),
        "best_algorithm": result.get("best_algorithm"),
        "hopkins_statistic": result.get("hopkins_statistic"),
        "lineage": result.get("lineage", {}),
    })
    files[f"{prefix}/parameters.json"] = json.dumps(params, indent=2).encode("utf-8")
    files[f"{prefix}/requirements.txt"] = get_requirements_txt().encode("utf-8")
    files[f"{prefix}/README.md"] = get_readme(run_id).encode("utf-8")

    # Notebook
    safe_result = sanitize_for_json(result)
    nb = build_notebook(run_id, safe_result, sanitize_for_json(data))
    errors = validate_notebook_syntax(nb)
    if errors:
        raise ValueError("Notebook syntax invalid: " + "; ".join(errors[:3]))
    files[f"{prefix}/analysis_{run_id}.ipynb"] = notebook_to_bytes(nb)

    # Figures dir placeholder
    files[f"{prefix}/figures/.gitkeep"] = b""

    return files


def build_zip_bundle(run_id: str, result: dict, data: dict) -> bytes:
    """Create complete analyst ZIP."""
    files = prepare_bundle_data(run_id, result, data)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in files.items():
            zf.writestr(path, content)
    buf.seek(0)
    return buf.read()


def try_execute_notebook(run_id: str, result: dict, data: dict) -> tuple[bytes | None, str | None]:
    """Attempt notebook execution; return (executed_bytes, error_message)."""
    try:
        import nbformat
        from nbconvert.preprocessors import ExecutePreprocessor
    except ImportError:
        return None, "nbformat/nbconvert not installed — source notebook only"

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / f"market_cluster_{run_id}"
        root.mkdir()
        files = prepare_bundle_data(run_id, result, data)
        for rel, content in files.items():
            path = Path(tmp) / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

        nb_path = root / f"analysis_{run_id}.ipynb"
        nb = nbformat.read(str(nb_path), as_version=4)
        ep = ExecutePreprocessor(timeout=120, kernel_name="python3")
        try:
            ep.preprocess(nb, {"metadata": {"path": str(root)}})
            out_path = root / f"analysis_{run_id}_executed.ipynb"
            nbformat.write(nb, str(out_path))
            return out_path.read_bytes(), None
        except Exception as e:
            return None, str(e)
