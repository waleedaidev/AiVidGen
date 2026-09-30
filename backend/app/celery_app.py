"""Celery app. On Windows run the worker with the threads pool (prefork isn't supported):
    celery -A app.celery_app worker --pool=threads --concurrency=4 --loglevel=info
"""

import logging

from celery import Celery

from app.config import get_settings

settings = get_settings()
logging.basicConfig(level=logging.INFO)

app = Celery("aividgen", broker=settings.redis_url, backend=settings.redis_url, include=["app.tasks"])

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=60 * 60,
    broker_connection_retry_on_startup=True,
)
