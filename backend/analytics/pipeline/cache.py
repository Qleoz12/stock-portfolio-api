"""Pipeline stage cache with deterministic hashes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Optional

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "analytics_cache"


def _hash_dict(data: dict) -> str:
    payload = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


class PipelineCache:
    def __init__(self, run_prefix: str = "") -> None:
        self.run_prefix = run_prefix
        self.dir = CACHE_DIR / run_prefix if run_prefix else CACHE_DIR
        self.dir.mkdir(parents=True, exist_ok=True)
        self._memory: dict[str, Any] = {}

    def key(self, stage: str, inputs: dict) -> str:
        return f"{stage}_{_hash_dict(inputs)}"

    def get(self, stage: str, inputs: dict) -> Optional[Any]:
        k = self.key(stage, inputs)
        if k in self._memory:
            return self._memory[k]
        path = self.dir / f"{k}.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            self._memory[k] = data
            return data
        return None

    def set(self, stage: str, inputs: dict, output: Any) -> str:
        k = self.key(stage, inputs)
        self._memory[k] = output
        path = self.dir / f"{k}.json"
        path.write_text(json.dumps(output, default=str), encoding="utf-8")
        return k

    def invalidate_from(self, stage: str, stages_order: list[str]) -> None:
        """Invalidate this stage and all downstream stages."""
        try:
            idx = stages_order.index(stage)
        except ValueError:
            return
        for s in stages_order[idx:]:
            for p in self.dir.glob(f"{s}_*.json"):
                p.unlink(missing_ok=True)


STAGE_ORDER = [
    "universe", "raw_data", "validation", "features", "transform",
    "missing_values", "outliers", "scaling", "distance_matrix",
    "tendency", "optimal_k", "clustering", "validation_metrics", "interpretation",
]
