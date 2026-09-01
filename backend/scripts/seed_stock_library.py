"""Run offline (manually or via cron) to pre-fetch a small tagged stock-video library used as
the retry-exhausted fallback. Never called live during a user's chat/generation flow.

Usage:
    cd backend
    python -m scripts.seed_stock_library
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import get_settings
from app.db import SessionLocal, init_db
from app.providers.stock_library import fetch_and_store_pexels_clips

QUERIES = {
    "restaurant": "restaurant food cooking",
    "fitness": "gym workout fitness",
    "real_estate": "modern house interior",
    "fashion": "fashion clothing model",
    "salon": "beauty salon spa",
    "retail": "retail shop store product",
    "other": "business office professional",
}


def main():
    settings = get_settings()
    if not settings.pexels_api_key:
        print("PEXELS_API_KEY not set in .env — nothing to seed. Set it and re-run.")
        return

    init_db()
    db = SessionLocal()
    clips_dir = os.path.join(settings.storage_dir_abs, "stock_library")

    total = 0
    try:
        for tag, query in QUERIES.items():
            count = fetch_and_store_pexels_clips(
                settings.pexels_api_key, tag, query, clips_dir, db, count=3
            )
            print(f"{tag}: stored {count} clips")
            total += count
    finally:
        db.close()

    print(f"Done. {total} clips stored in {clips_dir}")


if __name__ == "__main__":
    main()
