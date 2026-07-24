"""Yahoo Finance news + local VADER sentiment grouped by day."""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import yfinance as yf

from logger import get_logger
from services.sentiment_utils import score_text, weekly_label

log = get_logger("news_sentiment")

_CACHE: Dict[str, Any] = {}
_CACHE_TTL_SEC = 6 * 60 * 60


def _parse_pub_date(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        try:
            return datetime.fromtimestamp(raw, tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None
    if isinstance(raw, str) and raw.strip():
        s = raw.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            return None
    return None


def _normalize_yahoo_item(item: dict) -> Optional[dict]:
    """Support yfinance v0.2+ nested content and legacy flat shape."""
    content = item.get("content")
    if isinstance(content, dict):
        title = (content.get("title") or "").strip()
        pub_raw = content.get("pubDate") or content.get("displayTime")
        for url_key in ("clickThroughUrl", "canonicalUrl"):
            url_obj = content.get(url_key)
            if isinstance(url_obj, dict) and url_obj.get("url"):
                url = url_obj["url"]
                break
        else:
            url = ""
        provider = content.get("provider") or {}
        source = provider.get("displayName") if isinstance(provider, dict) else ""
    else:
        title = (item.get("title") or "").strip()
        pub_raw = item.get("providerPublishTime") or item.get("pubDate")
        url = item.get("link") or ""
        ct = item.get("content") or {}
        if not url and isinstance(ct, dict):
            for url_key in ("clickThroughUrl", "canonicalUrl"):
                url_obj = ct.get(url_key)
                if isinstance(url_obj, dict) and url_obj.get("url"):
                    url = url_obj["url"]
                    break
        source = item.get("publisher") or item.get("publisherName") or ""

    if not title:
        return None
    ts = _parse_pub_date(pub_raw)
    compound, label = score_text(title)
    return {
        "title": title,
        "url": url or "",
        "source": source or "",
        "published_at": ts.isoformat() if ts else None,
        "score": round(compound, 3),
        "label": label,
    }


def fetch_yahoo_news(ticker_yf: str, days: int = 7) -> List[dict]:
    try:
        raw = yf.Ticker(ticker_yf).news or []
    except Exception as e:
        log.warning("yfinance news failed for %s: %s", ticker_yf, e)
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out: List[dict] = []
    for item in raw:
        norm = _normalize_yahoo_item(item)
        if not norm:
            continue
        pub = norm.get("published_at")
        if pub:
            try:
                dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                if dt < cutoff:
                    continue
            except ValueError:
                pass
        out.append(norm)
    return out


def group_by_day(articles: List[dict], days: int = 7) -> List[dict]:
    by_day: Dict[str, List[dict]] = defaultdict(list)
    for a in articles:
        pub = a.get("published_at")
        if pub:
            day = pub[:10]
        else:
            day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        by_day[day].append(a)

    result: List[dict] = []
    today = datetime.now(timezone.utc).date()
    for i in range(days):
        d = (today - timedelta(days=i)).isoformat()
        items = by_day.get(d, [])
        if not items:
            result.append(
                {
                    "date": d,
                    "article_count": 0,
                    "avg_sentiment": None,
                    "label": "neutral",
                    "headlines": [],
                }
            )
            continue
        scores = [x["score"] for x in items if x.get("score") is not None]
        avg = sum(scores) / len(scores) if scores else None
        _, day_label = score_text(" ".join(x["title"] for x in items[:5]))
        sorted_items = sorted(items, key=lambda x: abs(x.get("score") or 0), reverse=True)
        result.append(
            {
                "date": d,
                "article_count": len(items),
                "avg_sentiment": round(avg, 3) if avg is not None else None,
                "label": day_label,
                "headlines": sorted_items[:5],
            }
        )
    return result


def build_stock_news_sentiment(ticker_yf: str, days: int = 7, force_refresh: bool = False) -> dict:
    cache_key = f"{ticker_yf}:{days}"
    now = time.time()
    cached = _CACHE.get(cache_key)
    if not force_refresh and cached and now < cached.get("expires_at", 0):
        return cached["payload"]

    articles = fetch_yahoo_news(ticker_yf, days=days)
    by_day = group_by_day(articles, days=days)
    scores = [a["score"] for a in articles if a.get("score") is not None]
    weekly_avg = sum(scores) / len(scores) if scores else None

    payload = {
        "ticker": ticker_yf,
        "days": days,
        "weekly_sentiment": round(weekly_avg, 3) if weekly_avg is not None else None,
        "weekly_label": weekly_label(weekly_avg),
        "by_day": by_day,
        "article_count": len(articles),
        "source": "yfinance+vader",
    }
    _CACHE[cache_key] = {"payload": payload, "expires_at": now + _CACHE_TTL_SEC}
    return payload
