"""Download stock_unifier.db from a private GitHub Release if missing locally."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def download_db() -> int:
    db_path = os.environ.get("DATABASE_PATH", "/app/stock_unifier.db")
    if os.path.isfile(db_path) and os.path.getsize(db_path) > 0:
        print(f"[download_db] Using existing DB: {db_path}")
        return 0

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("DB_REPO", "Qleoz12/stock-portfolio-db").strip()
    tag = os.environ.get("DB_RELEASE_TAG", "v1.0.0").strip()
    asset_name = os.environ.get("DB_ASSET_NAME", "stock_unifier.db").strip()

    if not token:
        print("[download_db] GITHUB_TOKEN not set; cannot download private release DB", file=sys.stderr)
        return 1

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "stock-portfolio-api",
    }

    release_url = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
    print(f"[download_db] Fetching release {repo}@{tag} ...")
    try:
        with urllib.request.urlopen(urllib.request.Request(release_url, headers=headers)) as resp:
            release = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        print(f"[download_db] Failed to fetch release: {exc}", file=sys.stderr)
        return 1

    assets = release.get("assets") or []
    asset = next((a for a in assets if a.get("name") == asset_name), None)
    if not asset:
        names = ", ".join(a.get("name", "?") for a in assets) or "(none)"
        print(f"[download_db] Asset '{asset_name}' not found. Available: {names}", file=sys.stderr)
        return 1

    asset_id = asset["id"]
    download_url = f"https://api.github.com/repos/{repo}/releases/assets/{asset_id}"
    download_headers = {
        **headers,
        "Accept": "application/octet-stream",
    }
    print(f"[download_db] Downloading {asset_name} ...")
    try:
        with urllib.request.urlopen(urllib.request.Request(download_url, headers=download_headers)) as resp:
            data = resp.read()
    except urllib.error.HTTPError as exc:
        print(f"[download_db] Failed to download asset: {exc}", file=sys.stderr)
        return 1

    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(db_path, "wb") as fh:
        fh.write(data)

    print(f"[download_db] Saved {len(data)} bytes to {db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(download_db())
