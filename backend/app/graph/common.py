import logging
import os
from contextlib import contextmanager

from app.config import get_settings
from app.db import SessionLocal
from app.llm.openrouter_client import chat_completion_json
from app.models_db import GenerationJob

log = logging.getLogger("aividgen.pipeline")


@contextmanager
def session():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def job_dir(job_id: str, *sub: str) -> str:
    path = os.path.join(get_settings().storage_dir_abs, job_id, *sub)
    os.makedirs(path, exist_ok=True)
    return path


def set_status(job_id: str, status: str, **fields) -> None:
    with session() as db:
        job = db.get(GenerationJob, job_id)
        if job is None:
            return
        job.status = status
        for key, value in fields.items():
            setattr(job, key, value)
    log.info("job %s -> %s", job_id, status)


def llm_json(system: str, user: str, temperature: float = 0.7) -> dict | None:
    """One JSON-mode LLM call; None when there's no key or the call/parse fails so the
    caller can use its rule-based fallback."""
    try:
        return chat_completion_json(
            [{"role": "system", "content": system}, {"role": "user", "content": user}], temperature=temperature
        )
    except Exception as exc:  # noqa: BLE001 — any LLM failure means "use the fallback"
        log.warning("LLM step fell back to rules: %s", exc)
        return None
