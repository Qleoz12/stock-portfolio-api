"""Local VADER sentiment — no external LLM/API."""

from __future__ import annotations

from typing import Optional, Tuple

_analyzer = None


def _get_analyzer():
    global _analyzer
    if _analyzer is None:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

        _analyzer = SentimentIntensityAnalyzer()
    return _analyzer


def score_text(text: str) -> Tuple[float, str]:
    """Return (compound score -1..1, label: bullish|neutral|bearish)."""
    if not text or not str(text).strip():
        return 0.0, "neutral"
    compound = float(_get_analyzer().polarity_scores(str(text))["compound"])
    if compound >= 0.05:
        label = "bullish"
    elif compound <= -0.05:
        label = "bearish"
    else:
        label = "neutral"
    return compound, label


def weekly_label(avg: Optional[float]) -> str:
    if avg is None:
        return "neutral"
    if avg >= 0.05:
        return "bullish"
    if avg <= -0.05:
        return "bearish"
    if avg >= 0.02:
        return "slightly_bullish"
    if avg <= -0.02:
        return "slightly_bearish"
    return "neutral"
