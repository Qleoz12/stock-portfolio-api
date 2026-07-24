"""X/Twitter feeds via Nitter RSS — clean text cards, no embed widgets."""

from __future__ import annotations

import json
import os
import re
import time
from calendar import timegm
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any, Dict, List, Optional, Tuple

import feedparser
import httpx

from config import NITTER_INSTANCES
from logger import get_logger
from services.sentiment_utils import score_text

log = get_logger("x_feed")

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_SOURCES_PATH = os.path.join(_DATA_DIR, "x_feed_sources.json")

_CACHE: Dict[str, Any] = {"payload": None, "expires_at": 0.0}
_CACHE_TTL_SEC = 20 * 60

_TAG_RE = re.compile(r"<[^>]+>")
_NITTER_STATUS_RE = re.compile(
    r"https?://(?:nitter\.(?:net|cz|poast\.org)|[^/]+)/([^/]+)/status/(\d+)",
    re.I,
)


def _strip_html(text: str) -> str:
    if not text:
        return ""
    t = unescape(_TAG_RE.sub(" ", text))
    return re.sub(r"\s+", " ", t).strip()


def _parse_entry_date(entry: dict) -> Optional[datetime]:
    for key in ("published_parsed", "updated_parsed"):
        st = entry.get(key)
        if st:
            try:
                return datetime.fromtimestamp(timegm(st), tz=timezone.utc)
            except (ValueError, OverflowError, OSError):
                pass
    for key in ("published", "updated"):
        raw = entry.get(key)
        if raw:
            try:
                dt = parsedate_to_datetime(raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except (ValueError, TypeError):
                pass
    return None


def _rewrite_x_url(link: str, handle: str) -> str:
    if not link:
        return ""
    m = _NITTER_STATUS_RE.search(link)
    if m:
        user, status_id = m.group(1), m.group(2)
        return f"https://x.com/{user}/status/{status_id}"
    if "/status/" in link and "x.com" not in link and "twitter.com" not in link:
        sid = link.rsplit("/", 1)[-1].split("#")[0]
        if sid.isdigit():
            return f"https://x.com/{handle}/status/{sid}"
    return link


def _window_start(window: str) -> datetime:
    now = datetime.now(timezone.utc)
    w = (window or "24h").lower()
    if w in ("today", "hoy"):
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if w in ("7d", "week", "semana"):
        return now - timedelta(days=7)
    return now - timedelta(hours=24)


def load_sources() -> List[dict]:
    with open(_SOURCES_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("columns") or []


def _parse_feed_entries(content: bytes, handle: str) -> List[dict]:
    parsed = feedparser.parse(content)
    items: List[dict] = []
    for entry in parsed.entries or []:
        title = _strip_html(entry.get("title") or "")
        summary = _strip_html(entry.get("summary") or entry.get("description") or "")
        text = title
        if summary and summary != title and len(summary) > len(title):
            text = summary
        if not text or text.lower().startswith("rss reader not yet whitelisted"):
            continue
        published = _parse_entry_date(entry)
        link = _rewrite_x_url(entry.get("link") or entry.get("id") or "", handle)
        has_media = bool(entry.get("media_content") or entry.get("enclosures"))
        compound, label = score_text(text)
        items.append(
            {
                "handle": handle,
                "text": text,
                "published_at": published.isoformat() if published else None,
                "url": link,
                "sentiment": round(compound, 3),
                "sentiment_label": label,
                "has_media": has_media,
            }
        )
    return items


def _fetch_handle_rss(handle: str, client: httpx.Client) -> Tuple[List[dict], Optional[str]]:
    last_err: Optional[str] = None
    for base in NITTER_INSTANCES:
        url = f"{base}/{handle}/rss"
        try:
            r = client.get(url, follow_redirects=True)
            if r.status_code == 404:
                last_err = f"@{handle} not found on {base}"
                continue
            if r.status_code >= 400:
                last_err = f"{base}: HTTP {r.status_code}"
                continue
            items = _parse_feed_entries(r.content, handle)
            if items:
                return items, None
            last_err = f"{base}: empty feed"
        except Exception as e:
            last_err = f"{base}: {e}"
            log.debug("Nitter %s @%s: %s", base, handle, e)
    log.warning("All Nitter instances failed for @%s: %s", handle, last_err)
    return [], last_err


def build_x_feeds(window: str = "24h", force_refresh: bool = False) -> dict:
    now = time.time()
    cache_key = f"{window}"
    if (
        not force_refresh
        and _CACHE.get("key") == cache_key
        and _CACHE.get("payload")
        and now < (_CACHE.get("expires_at") or 0)
    ):
        return _CACHE["payload"]

    start = _window_start(window)
    columns_cfg = load_sources()
    columns_out: List[dict] = []
    errors: List[str] = []

    with httpx.Client(timeout=18.0, headers={"User-Agent": "Mozilla/5.0 (compatible; StockUnifier/1.0)"}) as client:
        for col in columns_cfg:
            col_items: List[dict] = []
            for handle in col.get("handles") or []:
                try:
                    raw, err = _fetch_handle_rss(handle, client)
                    if err:
                        errors.append(f"@{handle}: {err}")
                    for item in raw:
                        pub = item.get("published_at")
                        if pub:
                            try:
                                dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                                if dt < start:
                                    continue
                            except ValueError:
                                pass
                        col_items.append(item)
                except Exception as e:
                    errors.append(f"@{handle}: {e}")
                    log.warning("Handle @%s error: %s", handle, e)

            col_items.sort(
                key=lambda x: x.get("published_at") or "",
                reverse=True,
            )
            columns_out.append(
                {
                    "id": col.get("id"),
                    "label": col.get("label"),
                    "items": col_items[:40],
                }
            )

    payload = {
        "window": window,
        "columns": columns_out,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "nitter",
        "rsshub_base": ", ".join(NITTER_INSTANCES),
        "errors": errors,
    }
    _CACHE["key"] = cache_key
    _CACHE["payload"] = payload
    _CACHE["expires_at"] = now + _CACHE_TTL_SEC
    return payload
