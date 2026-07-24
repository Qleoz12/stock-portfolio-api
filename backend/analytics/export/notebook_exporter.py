"""Reproducible Jupyter notebook export for clustering runs."""
from __future__ import annotations

import json
import pprint
import re
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


def python_repr(value: Any) -> str:
    """Serialize a value as valid Python literal (not JSON)."""
    if isinstance(value, Enum):
        return repr(value.value)
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float):
        if value != value:  # NaN
            return "float('nan')"
        if value == float("inf"):
            return "float('inf')"
        if value == float("-inf"):
            return "float('-inf')"
        return repr(value)
    if isinstance(value, (int, str)):
        return repr(value)
    if isinstance(value, dict):
        items = [f"{repr(k)}: {python_repr(v)}" for k, v in value.items()]
        if not items:
            return "{}"
        inner = ",\n    ".join(items)
        return "{\n    " + inner + "\n}"
    if isinstance(value, (list, tuple)):
        if not value:
            return "[]"
        if len(value) <= 5 and all(isinstance(x, (int, float, str, bool, type(None))) for x in value):
            return repr(list(value))
        inner = ",\n    ".join(python_repr(v) for v in value)
        return "[\n    " + inner + "\n]"
    return repr(value)


def _lines(*parts: str) -> list[str]:
    """Build nbformat source lines; each line ends with \\n per spec."""
    text = "\n".join(p for p in parts if p is not None)
    if not text.endswith("\n"):
        text += "\n"
    return [line + ("\n" if not line.endswith("\n") else "") for line in text.split("\n")[:-1]] + ([text.split("\n")[-1] + "\n"] if text.split("\n")[-1] else [])


def _md_cell(*parts: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": _lines(*parts)}


def _code_cell(*parts: str) -> dict:
    return {
        "cell_type": "code",
        "metadata": {},
        "source": _lines(*parts),
        "outputs": [],
        "execution_count": None,
    }


def build_notebook(run_id: str, result: dict, data: dict) -> dict:
    """Build executable source notebook with relative data paths."""
    mode = result.get("mode")
    if isinstance(mode, Enum):
        mode = mode.value

    params = {
        "run_id": run_id,
        "universe_id": result.get("universe_id"),
        "mode": mode,
        "features_used": result.get("features_used", []),
        "k_recommended": result.get("k_recommended"),
        "best_algorithm": result.get("best_algorithm"),
        "random_seed": result.get("lineage", {}).get("random_seed", 42),
        "period_days": result.get("lineage", {}).get("time_window", "365d"),
    }

    cells = [
        _md_cell(
            f"# Market Cluster Explorer — Run `{run_id}`",
            "",
            f"Exported: {datetime.utcnow().isoformat()}Z",
            "",
            "This notebook loads exported datasets from the `data/` folder using relative paths.",
            "No Yahoo Finance or database access required.",
        ),
        _code_cell(
            "from pathlib import Path",
            "import json",
            "import warnings",
            "warnings.filterwarnings('ignore')",
            "",
            "import numpy as np",
            "import pandas as pd",
            "import matplotlib.pyplot as plt",
            "import seaborn as sns",
            "",
            "DATA_DIR = Path('data')",
            "FIGURE_DIR = Path('figures')",
            "FIGURE_DIR.mkdir(exist_ok=True)",
            "",
            "sns.set_theme(style='whitegrid')",
            "plt.rcParams['figure.figsize'] = (10, 6)",
        ),
        _code_cell(
            "PARAMETERS = " + python_repr(params),
            "with open('parameters.json', 'r', encoding='utf-8') as f:",
            "    PARAMETERS = json.load(f)",
            "PARAMETERS",
        ),
        _md_cell("## Load exported datasets"),
        _code_cell(
            "raw_df = pd.read_parquet(DATA_DIR / 'raw_dataset.parquet')",
            "clean_df = pd.read_parquet(DATA_DIR / 'clean_dataset.parquet')",
            "scaled_df = pd.read_parquet(DATA_DIR / 'scaled_features.parquet')",
            "assignments_df = pd.read_csv(DATA_DIR / 'cluster_assignments.csv')",
            "print(f'Assets: {len(raw_df)}, Features: {scaled_df.shape[1] - 1}')",
            "raw_df.head()",
        ),
        _md_cell("## Universe coverage"),
        _code_cell(
            "coverage_df = pd.read_csv(DATA_DIR / 'universe_coverage.csv')",
            "coverage_df",
        ),
        _md_cell("## Data quality"),
        _code_cell(
            "issues_df = pd.read_csv(DATA_DIR / 'validation_issues.csv')",
            "issues_df.head(10) if len(issues_df) else 'No issues recorded'",
        ),
        _md_cell("## Feature catalog"),
        _code_cell(
            "features_df = pd.read_csv(DATA_DIR / 'feature_catalog.csv')",
            "features_df",
        ),
        _md_cell("## Hopkins statistic (recomputed from scaled matrix)"),
        _code_cell(
            "from sklearn.neighbors import NearestNeighbors",
            "",
            "def hopkins_statistic(X, sample_size=None, random_state=42):",
            "    rng = np.random.default_rng(random_state)",
            "    n, d = X.shape",
            "    if n < 10:",
            "        return 0.5",
            "    m = sample_size or min(int(n * 0.1), 50)",
            "    m = max(5, min(m, n - 1))",
            "    mins, maxs = X.min(axis=0), X.max(axis=0)",
            "    span = maxs - mins",
            "    span[span == 0] = 1.0",
            "    u = rng.random((m, d)) * span + mins",
            "    idx = rng.choice(n, size=m, replace=False)",
            "    nn = NearestNeighbors(n_neighbors=2).fit(X)",
            "    w = nn.kneighbors(u)[0][:, 0].sum()",
            "    v = nn.kneighbors(X[idx])[0][:, 1].sum()",
            "    return float(v / (w + v)) if (w + v) else 0.5",
            "",
            "feature_cols = [c for c in scaled_df.columns if c != 'ticker']",
            "X = scaled_df[feature_cols].values",
            "hopkins = hopkins_statistic(X, random_state=PARAMETERS.get('random_seed', 42))",
            "print(f'Hopkins statistic: {hopkins:.4f}')",
            f"print(f'App reported: {result.get('hopkins_statistic')!r}')",
        ),
        _md_cell("## VAT heatmap"),
        _code_cell(
            "from scipy.spatial.distance import pdist, squareform",
            "dist = squareform(pdist(X, metric='euclidean'))",
            "tickers = scaled_df['ticker'].tolist()",
            "plt.figure(figsize=(8, 7))",
            "sns.heatmap(dist, xticklabels=tickers, yticklabels=tickers, cmap='viridis')",
            "plt.title('VAT Distance Matrix')",
            "plt.tight_layout()",
            "plt.savefig(FIGURE_DIR / 'vat.png', dpi=120)",
            "plt.show()",
        ),
        _md_cell("## Optimal K metrics"),
        _code_cell(
            "optimal_k = json.loads((DATA_DIR / 'optimal_k.json').read_text(encoding='utf-8'))",
            "optimal_k",
        ),
        _md_cell("## Silhouette by K"),
        _code_cell(
            "sil_scores = optimal_k.get('silhouette', {})",
            "if sil_scores:",
            "    ks = sorted(int(k) for k in sil_scores)",
            "    vals = [sil_scores[str(k)] for k in ks]",
            "    plt.figure()",
            "    plt.plot(ks, vals, 'o-')",
            "    plt.xlabel('K')",
            "    plt.ylabel('Silhouette')",
            "    plt.title('Silhouette by K')",
            "    plt.savefig(FIGURE_DIR / 'silhouette_by_k.png', dpi=120)",
            "    plt.show()",
        ),
        _md_cell("## Gap statistic"),
        _code_cell(
            "gap_scores = optimal_k.get('gap', {})",
            "if gap_scores:",
            "    ks = sorted(int(k) for k in gap_scores)",
            "    vals = [gap_scores[str(k)] for k in ks]",
            "    plt.figure()",
            "    plt.bar(ks, vals)",
            "    plt.xlabel('K')",
            "    plt.ylabel('Gap')",
            "    plt.title('Gap Statistic')",
            "    plt.savefig(FIGURE_DIR / 'gap_statistic.png', dpi=120)",
            "    plt.show()",
        ),
        _md_cell("## Algorithm comparison"),
        _code_cell(
            "ranking_df = pd.read_csv(DATA_DIR / 'algorithm_ranking.csv')",
            "ranking_df",
        ),
        _md_cell("## PCA scatterplot"),
        _code_cell(
            "from sklearn.decomposition import PCA",
            "pca = PCA(n_components=2)",
            "coords = pca.fit_transform(X)",
            "pca_df = pd.DataFrame(coords, columns=['PC1', 'PC2'])",
            "pca_df['ticker'] = tickers",
            "pca_df = pca_df.merge(assignments_df[['ticker', 'cluster_id']], on='ticker')",
            "plt.figure()",
            "for cid in sorted(pca_df['cluster_id'].unique()):",
            "    sub = pca_df[pca_df['cluster_id'] == cid]",
            "    plt.scatter(sub['PC1'], sub['PC2'], label=f'Cluster {cid}', alpha=0.8)",
            "plt.legend()",
            "plt.title('PCA — Cluster Assignments')",
            "plt.savefig(FIGURE_DIR / 'pca_clusters.png', dpi=120)",
            "plt.show()",
        ),
        _md_cell("## Final silhouette plot"),
        _code_cell(
            "from sklearn.metrics import silhouette_samples",
            "labels = assignments_df.set_index('ticker').reindex(tickers)['cluster_id'].values",
            "sil = silhouette_samples(X, labels)",
            "y_lower = 10",
            "plt.figure(figsize=(10, 5))",
            "for cid in sorted(np.unique(labels)):",
            "    cid_sil = sil[labels == cid]",
            "    cid_sil.sort()",
            "    size = cid_sil.shape[0]",
            "    plt.bar(range(y_lower, y_lower + size), cid_sil, width=1)",
            "    y_lower += size + 10",
            "plt.axhline(sil.mean(), color='red', linestyle='--', label=f'Mean={sil.mean():.3f}')",
            "plt.ylabel('Silhouette')",
            "plt.title('Silhouette Samples by Cluster')",
            "plt.legend()",
            "plt.savefig(FIGURE_DIR / 'final_silhouette.png', dpi=120)",
            "plt.show()",
        ),
        _md_cell("## Cluster assignments"),
        _code_cell("assignments_df"),
        _md_cell("## Cluster profiles"),
        _code_cell(
            "profile_cols = [c for c in clean_df.columns if c not in ('ticker', 'sector')][:6]",
            "profiles = assignments_df.merge(clean_df, on='ticker').groupby('cluster_id')[profile_cols].mean()",
            "profiles",
        ),
        _md_cell("## Limitations"),
        _md_cell(
            "- Results are exploratory when Hopkins < 0.55.",
            "- Cluster count was selected by consensus of multiple metrics.",
            "- Financial interpretation requires domain expertise.",
            "",
            "## Reproducibility",
            f"- Run ID: `{run_id}`",
            f"- Generated: {datetime.utcnow().isoformat()}Z",
        ),
    ]

    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.11.0"},
        },
        "cells": cells,
    }


def validate_notebook_syntax(nb: dict) -> list[str]:
    """Compile every code cell; return list of errors."""
    errors: list[str] = []
    invalid_patterns = [
        (r"(?<![\"'])null(?![\"'])", "JSON null found"),
        (r"(?<![\"'])false(?![\"'])", "JSON false found"),
        (r"pdassignments", "Missing newline after pd"),
        (r"pddf", "Missing newline after pd"),
    ]
    for i, cell in enumerate(nb.get("cells", [])):
        if cell.get("cell_type") != "code":
            continue
        source = "".join(cell.get("source", []))
        for pattern, msg in invalid_patterns:
            if re.search(pattern, source):
                errors.append(f"Cell {i}: {msg}")
        try:
            compile(source, f"cell_{i}", "exec")
        except SyntaxError as e:
            errors.append(f"Cell {i} syntax error: {e}")
    return errors


def notebook_to_bytes(nb: dict) -> bytes:
    errors = validate_notebook_syntax(nb)
    if errors:
        raise ValueError("Notebook validation failed: " + "; ".join(errors[:5]))
    return json.dumps(nb, indent=2, ensure_ascii=False).encode("utf-8")


def get_requirements_txt() -> str:
    return "\n".join([
        "numpy>=1.24",
        "pandas>=2.0",
        "scipy>=1.10",
        "scikit-learn>=1.3",
        "matplotlib>=3.7",
        "seaborn>=0.13",
        "pyarrow>=14.0",
        "openpyxl>=3.1",
    ]) + "\n"


def get_readme(run_id: str) -> str:
    return f"""# Market Cluster Analysis — {run_id}

## Quick start

```bash
pip install -r requirements.txt
jupyter notebook analysis_{run_id}.ipynb
```

Or execute headless:

```bash
jupyter nbconvert --to notebook --execute analysis_{run_id}.ipynb --output analysis_{run_id}_executed.ipynb
jupyter nbconvert --to html analysis_{run_id}_executed.ipynb
```

## Contents

- `data/` — exported datasets (Parquet/CSV)
- `figures/` — generated plots (created on execution)
- `parameters.json` — run configuration
- `analysis_{run_id}.ipynb` — source notebook

All paths are relative. No database or Yahoo Finance required.
"""
