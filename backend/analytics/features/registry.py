"""Central feature registry with profiles."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml

from analytics.features.discovery import discover_all
from analytics.models.feature_definition import FeatureDefinition, FeatureProfile

PROFILES_PATH = Path(__file__).parent / "profiles.yaml"

DEFAULT_PROFILES: dict[str, FeatureProfile] = {
    "ALL_CLUSTERING_ELIGIBLE_FEATURES": FeatureProfile(
        name="ALL_CLUSTERING_ELIGIBLE_FEATURES",
        display_name="All Clustering-Eligible Features",
        description="Numeric features eligible for clustering (default).",
    ),
    "ALL_VALID_FINANCIAL_FEATURES": FeatureProfile(
        name="ALL_VALID_FINANCIAL_FEATURES",
        display_name="All Valid Financial Features (legacy)",
        description="Alias for ALL_CLUSTERING_ELIGIBLE_FEATURES.",
    ),
    "CORE_RISK_RETURN": FeatureProfile(
        name="CORE_RISK_RETURN",
        display_name="Core Risk and Return",
        description="Return, volatility, beta, drawdown, average correlation.",
        feature_names=[
            "annualized_return", "volatility_1y", "beta", "max_drawdown", "average_correlation",
        ],
    ),
    "TECHNICAL": FeatureProfile(
        name="TECHNICAL",
        display_name="Technical Indicators",
        feature_names=["ema_20", "ema_52", "ema_200", "macd", "macd_signal", "rsi_14"],
    ),
    "FUNDAMENTALS": FeatureProfile(
        name="FUNDAMENTALS",
        display_name="Fundamentals",
        feature_names=[
            "net_income_margin", "return_on_assets", "fcf_yield", "debt_to_equity",
            "health_score", "div_yield_ttm",
        ],
    ),
    "DIVIDEND": FeatureProfile(
        name="DIVIDEND",
        display_name="Dividend Portfolio",
        feature_names=[
            "div_yield_ttm", "dividend_ttm", "payments_ttm", "dividend_score", "payout_ratio",
        ],
    ),
}


class FeatureRegistry:
    """Central registry of feature definitions and profiles."""

    def __init__(self) -> None:
        self._features: dict[str, FeatureDefinition] = {}
        self._profiles: dict[str, FeatureProfile] = {}
        self.reload()

    def reload(self) -> None:
        self._features = {f.name: f for f in discover_all()}
        self._profiles = dict(DEFAULT_PROFILES)
        if PROFILES_PATH.exists():
            data = yaml.safe_load(PROFILES_PATH.read_text(encoding="utf-8")) or {}
            for name, cfg in data.get("profiles", {}).items():
                self._profiles[name] = FeatureProfile(
                    name=name,
                    display_name=cfg.get("display_name", name),
                    description=cfg.get("description", ""),
                    feature_names=cfg.get("features", []),
                )

    @property
    def features(self) -> list[FeatureDefinition]:
        return list(self._features.values())

    def get(self, name: str) -> Optional[FeatureDefinition]:
        return self._features.get(name)

    def get_profile(self, name: str) -> Optional[FeatureProfile]:
        return self._profiles.get(name)

    def list_profiles(self) -> list[FeatureProfile]:
        return list(self._profiles.values())

    def resolve_profile_features(
        self,
        profile_name: str,
        available_columns: Optional[set[str]] = None,
        max_missing_pct: float = 0.30,
        df=None,
    ) -> list[str]:
        """Resolve feature names for a profile, applying quality filters."""
        if profile_name in ("ALL_CLUSTERING_ELIGIBLE_FEATURES", "ALL_VALID_FINANCIAL_FEATURES"):
            from analytics.features.transformations import RAW_PRICE_COLS, RAW_SIZE_COLS, is_clustering_eligible
            candidates = []
            for f in self._features.values():
                if not f.clustering_enabled or f.data_leakage_risk:
                    continue
                eligible, _ = is_clustering_eligible(f.name)
                if not eligible:
                    continue
                if f.name in RAW_PRICE_COLS or f.name in RAW_SIZE_COLS:
                    continue
                candidates.append(f.name)
        else:
            profile = self._profiles.get(profile_name)
            if not profile:
                return []
            candidates = profile.feature_names

        if available_columns is not None:
            candidates = [c for c in candidates if c in available_columns]

        if df is not None:
            filtered = []
            for col in candidates:
                if col not in df.columns:
                    continue
                series = df[col]
                if series.nunique(dropna=True) <= 1:
                    continue
                missing = series.isna().mean()
                if missing > max_missing_pct:
                    continue
                filtered.append(col)
            return filtered

        return candidates

    def to_dict(self) -> dict:
        return {
            "features": [f.model_dump() for f in self.features],
            "profiles": [p.model_dump() for p in self.list_profiles()],
        }


_registry: Optional[FeatureRegistry] = None


def get_registry() -> FeatureRegistry:
    global _registry
    if _registry is None:
        _registry = FeatureRegistry()
    return _registry
