import os

from fastapi import FastAPI, BackgroundTasks, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db, init_db
from app.graph.graph import get_graph
from app.chat.chat_llm import start_chat, handle_turn
from app.models_db import Lead, GenerationJob
from app.schemas import (
    StartRequest, StartResponse, ChatTurnRequest, ChatTurnResponse, JobStatusResponse,
)

settings = get_settings()

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")
STORAGE_DIR = settings.storage_dir_abs
os.makedirs(STORAGE_DIR, exist_ok=True)

app = FastAPI(title="AiVidGen")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


def _run_generation_job(job_id: str, lead_id: str, raw_prompt: str):
    graph = get_graph()
    graph.invoke({
        "job_id": job_id,
        "lead_id": lead_id,
        "raw_prompt": raw_prompt,
        "attempt_count": 0,
        "max_attempts": settings.max_generation_attempts,
        "used_fallback": False,
    })


@app.post("/api/start", response_model=StartResponse)
def start(req: StartRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    if not req.prompt or not req.prompt.strip():
        raise HTTPException(400, "prompt is required")

    lead = Lead(raw_prompt=req.prompt.strip())
    db.add(lead)
    db.commit()
    db.refresh(lead)

    job = GenerationJob(lead_id=lead.id)
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(_run_generation_job, job.id, lead.id, lead.raw_prompt)

    first_message = start_chat(lead, db)

    return StartResponse(lead_id=lead.id, job_id=job.id, first_message=first_message)


@app.post("/api/chat", response_model=ChatTurnResponse)
def chat(req: ChatTurnRequest, db: Session = Depends(get_db)):
    lead = db.get(Lead, req.lead_id)
    if lead is None:
        raise HTTPException(404, "lead not found")

    reply, done = handle_turn(lead, req.message, db)
    return ChatTurnResponse(reply=reply, done=done, awaiting_video=done)


@app.get("/api/status/{job_id}", response_model=JobStatusResponse)
def status(job_id: str, db: Session = Depends(get_db)):
    job = db.get(GenerationJob, job_id)
    if job is None:
        raise HTTPException(404, "job not found")

    video_url = None
    if job.video_path and job.status == "done":
        video_url = f"/storage/{os.path.relpath(job.video_path, STORAGE_DIR).replace(os.sep, '/')}"

    return JobStatusResponse(
        job_id=job.id, status=job.status, used_fallback=job.used_fallback, video_url=video_url,
    )


app.mount("/storage", StaticFiles(directory=STORAGE_DIR), name="storage")
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
