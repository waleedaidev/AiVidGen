from app.celery_app import app
from app.jobs import run_pipeline, run_reshoot, run_reassemble


@app.task(name="aividgen.pipeline")
def pipeline_task(job_id: str) -> None:
    run_pipeline(job_id)


@app.task(name="aividgen.reshoot")
def reshoot_task(job_id: str) -> None:
    run_reshoot(job_id)


@app.task(name="aividgen.reassemble")
def reassemble_task(job_id: str) -> None:
    run_reassemble(job_id)
