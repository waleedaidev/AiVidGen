"""Pre-fetched industry-tagged stock clips, used only when real generation has failed
MAX_GENERATION_ATTEMPTS times. Fetching happens offline via scripts/seed_stock_library.py
(cron/manual) — never live during a user's retry, to avoid extra latency and rate limits.
"""

import random

from sqlalchemy.orm import Session

from app.models_db import StockClip

PEXELS_SEARCH_URL = "https://api.pexels.com/videos/search"


def fetch_and_store_pexels_clips(api_key: str, industry_tag: str, query: str, storage_dir: str, db: Session, count: int = 3) -> int:
    """Called by scripts/seed_stock_library.py. Downloads a few clips per industry tag
    and registers them in the stock_clips table. Returns how many were stored."""
    import os
    import httpx

    os.makedirs(storage_dir, exist_ok=True)
    resp = httpx.get(
        PEXELS_SEARCH_URL,
        headers={"Authorization": api_key},
        params={"query": query, "per_page": count},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    stored = 0
    for video in data.get("videos", []):
        files = sorted(video.get("video_files", []), key=lambda f: f.get("width") or 0)
        if not files:
            continue
        file_url = files[len(files) // 2]["link"]  # a mid-quality file, not the biggest
        file_path = os.path.join(storage_dir, f"{industry_tag}_{video['id']}.mp4")

        with httpx.stream("GET", file_url, timeout=60) as r:
            r.raise_for_status()
            with open(file_path, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=8192):
                    f.write(chunk)

        db.add(StockClip(
            industry_tag=industry_tag,
            source="pexels",
            file_path=file_path,
            description=query,
        ))
        stored += 1

    db.commit()
    return stored


def pick_fallback_clip(db: Session, industry_tag: str | None) -> StockClip | None:
    query = db.query(StockClip)
    if industry_tag:
        matches = query.filter(StockClip.industry_tag == industry_tag).all()
        if matches:
            return random.choice(matches)
    any_clips = query.all()
    return random.choice(any_clips) if any_clips else None
