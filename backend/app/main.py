import logging
import os

from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.admin import router as admin_router
from app.chat.chat_llm import start_chat, handle_turn
from app.config import get_settings
from app.db import get_db, init_db
from app.delivery import deliver, video_url
from app.jobs import dispatch
from app.models_db import Lead, GenerationJob
from app.schemas import StartRequest, StartResponse, ChatTurnRequest, ChatTurnResponse, JobStatusResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
settings = get_settings()

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(os.path.dirname(BACKEND_DIR), "frontend")
STORAGE_DIR = settings.storage_dir_abs
os.makedirs(STORAGE_DIR, exist_ok=True)

PROGRESS = {
    "queued": 2, "analyzing_brief": 8, "writing_script": 15, "extracting_characters": 22,
    "generating_references": 30, "generating_audio": 38, "planning_scenes": 44, "mapping_interactions": 50,
    "planning_shots": 55, "building_prompts": 60, "generating_shots": 75, "quality_check": 85,
    "repairing_prompts": 80, "assembling": 93, "awaiting_review": 97, "done": 100, "failed": 100,
}
UPSELL = (
    "This is your free teaser. Want the full-length video, more scenes or extra variations? "
    "Our team will contact you shortly on WhatsApp/email to unlock it."
)

app = FastAPI(title="AiVidGen")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(admin_router)


@app.on_event("startup")
def on_startup():
    init_db()


@app.post("/api/start", response_model=StartResponse)
def start(req: StartRequest, db: Session = Depends(get_db)):
    if not req.prompt or not req.prompt.strip():
        raise HTTPException(400, "prompt is required")

    lead = Lead(raw_prompt=req.prompt.strip())
    db.add(lead)
    db.commit()

    job = GenerationJob(lead_id=lead.id)
    db.add(job)
    db.commit()

    dispatch("pipeline", job.id)
    return StartResponse(lead_id=lead.id, job_id=job.id, first_message=start_chat(lead, db))


@app.post("/api/chat", response_model=ChatTurnResponse)
def chat(req: ChatTurnRequest, db: Session = Depends(get_db)):
    lead = db.get(Lead, req.lead_id)
    if lead is None:
        raise HTTPException(404, "lead not found")

    reply, done = handle_turn(lead, req.message, db)
    if done:
        for job in lead.jobs:
            deliver(job.id)
    return ChatTurnResponse(reply=reply, done=done, awaiting_video=done)


@app.get("/api/status/{job_id}", response_model=JobStatusResponse)
def status(job_id: str, db: Session = Depends(get_db)):
    job = db.get(GenerationJob, job_id)
    if job is None:
        raise HTTPException(404, "job not found")

    ready = job.status == "done"
    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        progress=PROGRESS.get(job.status, 50),
        used_fallback=job.used_fallback,
        video_url=video_url(job) if ready else None,
        upsell_message=UPSELL if ready or job.status == "awaiting_review" else None,
    )


app.mount("/storage", StaticFiles(directory=STORAGE_DIR), name="storage")
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
