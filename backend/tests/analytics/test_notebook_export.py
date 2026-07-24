"""Tests for notebook export and bundle generation."""
from __future__ import annotations

import sys
import os
import json
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from analytics.export.notebook_exporter import (
    build_notebook,
    validate_notebook_syntax,
    notebook_to_bytes,
    python_repr,
)


SAMPLE_RESULT = {
    "universe_id": "dow30",
    "mode": "feature",
    "features_used": ["beta", "volatility_1y"],
    "k_recommended": 4,
    "hopkins_statistic": 0.388256,
    "k_consensus": {"silhouette": 4, "elbow": 3},
    "best_algorithm": "kmeans",
    "lineage": {"random_seed": 42, "time_window": "365d"},
    "algorithms": [{
        "algorithm": "kmeans",
        "assignments": [{"ticker": "AAPL", "cluster_id": 0, "silhouette": 0.25}],
    }],
}

SAMPLE_DATA = {
    "df_records": [{"ticker": "AAPL", "beta": 1.2, "volatility_1y": 0.25}],
    "processed_records": [{"ticker": "AAPL", "beta": 0.5, "volatility_1y": -0.3}],
    "algorithm_ranking": [{"algorithm": "kmeans", "composite_score": 0.8, "rank": 1}],
    "optimal_k": {"consensus_k": 4, "silhouette": {"2": 0.2, "3": 0.25, "4": 0.3}, "gap": {"2": 0.1, "3": 0.2}},
    "tickers": ["AAPL"],
}


class TestPythonRepr:
    def test_none_bool_float(self):
        assert python_repr(None) == "None"
        assert python_repr(True) == "True"
        assert python_repr(False) == "False"
        assert "nan" in python_repr(float("nan"))

    def test_no_json_literals(self):
        s = python_repr({"a": None, "b": True, "c": False})
        assert "null" not in s
        assert "false" not in s
        assert "None" in s


class TestNotebookSyntax:
    def test_all_cells_compile(self):
        nb = build_notebook("testrun01", SAMPLE_RESULT, SAMPLE_DATA)
        errors = validate_notebook_syntax(nb)
        assert errors == [], f"Errors: {errors}"

    def test_no_concatenated_statements(self):
        nb = build_notebook("testrun01", SAMPLE_RESULT, SAMPLE_DATA)
        for i, cell in enumerate(nb["cells"]):
            if cell["cell_type"] != "code":
                continue
            source = "".join(cell["source"])
            assert "pdassignments" not in source, f"Cell {i}: missing newline after pd"
            assert "pddf" not in source, f"Cell {i}: missing newline after pd"
            assert "hopkins =" not in source or "k_consensus" not in source.replace("hopkins =", "", 1) or "\n" in source.split("hopkins =")[1].split("k_consensus")[0]

    def test_source_lines_end_with_newline(self):
        nb = build_notebook("testrun01", SAMPLE_RESULT, SAMPLE_DATA)
        for cell in nb["cells"]:
            if cell["cell_type"] == "code":
                for line in cell["source"]:
                    assert line.endswith("\n"), f"Line missing newline: {line!r}"

    def test_notebook_to_bytes_validates(self):
        nb = build_notebook("testrun01", SAMPLE_RESULT, SAMPLE_DATA)
        raw = notebook_to_bytes(nb)
        parsed = json.loads(raw.decode("utf-8"))
        assert parsed["nbformat"] == 4
        assert len(parsed["cells"]) >= 15

    def test_enum_mode_from_cache(self):
        from enum import Enum
        class Mode(str, Enum):
            FEATURE = "feature"
        result = dict(SAMPLE_RESULT)
        result["mode"] = Mode.FEATURE
        nb = build_notebook("testrun01", result, SAMPLE_DATA)
        errors = validate_notebook_syntax(nb)
        assert errors == [], f"Errors: {errors}"
        src = "".join(nb["cells"][2]["source"])
        assert "ClusteringMode" not in src
        assert "'feature'" in src

    def test_no_json_null_in_code_cells(self):
        nb = build_notebook("testrun01", SAMPLE_RESULT, SAMPLE_DATA)
        for cell in nb["cells"]:
            if cell["cell_type"] == "code":
                source = "".join(cell["source"])
                assert " null" not in source and "\nnull" not in source
                assert " false" not in source


class TestBundleBuilder:
    def test_prepare_bundle(self):
        from analytics.export.bundle_builder import prepare_bundle_data
        files = prepare_bundle_data("testrun01", SAMPLE_RESULT, SAMPLE_DATA)
        assert any("analysis_testrun01.ipynb" in k for k in files)
        assert any("parameters.json" in k for k in files)
        assert any("raw_dataset.parquet" in k for k in files)
        assert any("README.md" in k for k in files)

    def test_zip_bundle(self):
        from analytics.export.bundle_builder import build_zip_bundle
        z = build_zip_bundle("testrun01", SAMPLE_RESULT, SAMPLE_DATA)
        import zipfile, io
        with zipfile.ZipFile(io.BytesIO(z)) as zf:
            names = zf.namelist()
            assert any(n.endswith(".ipynb") for n in names)
            assert any("data/" in n for n in names)
