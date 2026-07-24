from datetime import datetime, timezone

from services.news_sentiment_service import group_by_day, _normalize_yahoo_item
from services.sentiment_utils import score_text, weekly_label


def test_normalize_yahoo_nested_content():
    item = {
        "id": "abc",
        "content": {
            "title": "Stock surges on strong earnings beat",
            "pubDate": "2026-05-21T10:00:00Z",
            "clickThroughUrl": {"url": "https://finance.yahoo.com/news/1.html"},
            "provider": {"displayName": "Yahoo Finance"},
        },
    }
    norm = _normalize_yahoo_item(item)
    assert norm is not None
    assert norm["title"] == "Stock surges on strong earnings beat"
    assert norm["url"].endswith("1.html")
    assert norm["source"] == "Yahoo Finance"


def test_normalize_yahoo_legacy_flat():
    item = {
        "title": "Legacy headline",
        "link": "https://finance.yahoo.com/news/2.html",
        "publisher": "Reuters",
        "providerPublishTime": 1716285600,
    }
    norm = _normalize_yahoo_item(item)
    assert norm is not None
    assert norm["title"] == "Legacy headline"


def test_score_text_bullish():
    score, label = score_text("Stock surges on strong earnings beat")
    assert label == "bullish"
    assert score > 0


def test_score_text_bearish():
    score, label = score_text("Company crashes after massive fraud scandal")
    assert label == "bearish"
    assert score < 0


def test_weekly_label():
    assert weekly_label(0.15) == "bullish"
    assert weekly_label(-0.15) == "bearish"
    assert weekly_label(0.0) == "neutral"
    assert weekly_label(None) == "neutral"


def test_group_by_day():
    articles = [
        {
            "title": "Good news",
            "url": "https://example.com/1",
            "source": "Reuters",
            "published_at": "2026-05-21T10:00:00+00:00",
            "score": 0.4,
            "label": "bullish",
        },
        {
            "title": "Bad news",
            "url": "https://example.com/2",
            "source": "Bloomberg",
            "published_at": "2026-05-21T14:00:00+00:00",
            "score": -0.3,
            "label": "bearish",
        },
        {
            "title": "Older headline",
            "url": "https://example.com/3",
            "source": "CNBC",
            "published_at": "2026-05-20T09:00:00+00:00",
            "score": 0.1,
            "label": "neutral",
        },
    ]
    # Patch "today" by using days=3 and checking structure
    result = group_by_day(articles, days=3)
    assert len(result) == 3
    day_with_articles = [d for d in result if d["article_count"] > 0]
    assert len(day_with_articles) == 2
    may21 = next(d for d in result if d["date"] == "2026-05-21")
    assert may21["article_count"] == 2
    assert len(may21["headlines"]) <= 5
