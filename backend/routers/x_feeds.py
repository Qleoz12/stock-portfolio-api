"""X feed reader — 3-column digest without Twitter embed widgets."""

import os
import sys

from fastapi import APIRouter, Query

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from services.x_feed_service import build_x_feeds

router = APIRouter(prefix="/api/x-feeds", tags=["x-feeds"])


@router.get("")
def get_x_feeds(
    window: str = Query("24h", description="today | 24h | 7d"),
    refresh: bool = Query(False, description="Bypass 20min cache"),
):
    return build_x_feeds(window=window, force_refresh=refresh)
