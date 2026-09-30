"""Job runners + dispatcher. Work goes to Celery (Redis) when a worker is alive, otherwise it runs
in a local thread so the app still works with no worker running."""

import logging
import threading
import traceback

from app.config import get_settings
from app.db import SessionLocal
from app.graph.graph import get_graph, get_reshoot_graph
from app.models_db import GenerationJob, Scene, Character

log = logging.getLogger("aividgen.jobs")
RECURSION_LIMIT = 60


def _fail(job_id: str, exc: Exception) -> None:
    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if job:
            job.status = "failed"
            job.error_log = f"{exc}\n{traceback.format_exc()[-3000:]}"
            db.commit()
    finally:
        db.close()
    log.exception("job %s failed", job_id)


def run_pipeline(job_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        state = {"job_id": job.id, "lead_id": job.lead_id, "raw_prompt": job.lead.raw_prompt}
        for scene in db.query(Scene).filter(Scene.job_id == job_id).all():
            db.delete(scene)
        db.query(Character).filter(Character.job_id == job_id).delete()
        job.attempt_count += 1
        job.delivered_at = None
        db.commit()
    finally:
        db.close()
    try:
        get_graph().invoke(state, {"recursion_limit": RECURSION_LIMIT})
    except Exception as exc:  # noqa: BLE001
        _fail(job_id, exc)


def run_reshoot(job_id: str) -> None:
    try:
        get_reshoot_graph().invoke({"job_id": job_id}, {"recursion_limit": RECURSION_LIMIT})
    except Exception as exc:  # noqa: BLE001
        _fail(job_id, exc)


def run_reassemble(job_id: str) -> None:
    from app.graph.production import assemble

    try:
        assemble({"job_id": job_id})
    except Exception as exc:  # noqa: BLE001
        _fail(job_id, exc)


RUNNERS = {"pipeline": run_pipeline, "reshoot": run_reshoot, "reassemble": run_reassemble}


def _worker_alive() -> bool:
    try:
        from app.celery_app import app as celery_app

        return bool(celery_app.control.ping(timeout=1.0))
    except Exception:  # noqa: BLE001 — broker down means "no worker"
        return False


def dispatch(kind: str, job_id: str) -> str:
    if get_settings().use_celery and _worker_alive():
        from app import tasks

        getattr(tasks, f"{kind}_task").delay(job_id)
        return "celery"
    threading.Thread(target=RUNNERS[kind], args=(job_id,), daemon=True).start()
    return "thread"
