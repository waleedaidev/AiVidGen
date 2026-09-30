"""Human editor API: review the final video and every intermediate artifact, approve (-> delivery),
reject, regenerate single shots, re-assemble, or rerun the whole pipeline."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.delivery import deliver, storage_url as _url
from app.jobs import dispatch
from app.models_db import GenerationJob, Shot
from app.schemas import ReviewRequest, RegenerateShotRequest


def require_admin(x_admin_token: str | None = Header(default=None)):
    token = get_settings().admin_token
    if token and x_admin_token != token:
        raise HTTPException(401, "invalid admin token")


router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])


def _job_or_404(db: Session, job_id: str) -> GenerationJob:
    job = db.get(GenerationJob, job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return job


@router.get("/jobs")
def list_jobs(status: str | None = None, limit: int = 50, db: Session = Depends(get_db)):
    q = db.query(GenerationJob)
    if status:
        q = q.filter(GenerationJob.status == status)
    jobs = q.order_by(GenerationJob.created_at.desc()).limit(limit).all()
    return [
        {
            "job_id": j.id, "status": j.status, "review_status": j.review_status, "created_at": j.created_at,
            "prompt": j.lead.raw_prompt, "email": j.lead.email, "phone": j.lead.phone,
            "title": (j.brief or {}).get("title"), "video_url": _url(j.video_path), "used_fallback": j.used_fallback,
        }
        for j in jobs
    ]


@router.get("/jobs/{job_id}")
def job_detail(job_id: str, db: Session = Depends(get_db)):
    j = _job_or_404(db, job_id)
    return {
        "job_id": j.id, "status": j.status, "review_status": j.review_status, "review_notes": j.review_notes,
        "error_log": j.error_log, "delivery_log": j.delivery_log, "delivered_at": j.delivered_at,
        "lead": {k: getattr(j.lead, k) for k in ("raw_prompt", "business_type", "tone", "target_audience",
                                                 "use_case", "preferred_style", "email", "phone", "chat_status")},
        "brief": j.brief, "script": j.full_script, "video_url": _url(j.video_path),
        "characters": [
            {"id": c.id, "key": c.key, "name": c.name, "role": c.role, "appearance": c.appearance,
             "voice": c.voice, "reference_image": _url(c.reference_image_path)}
            for c in j.characters
        ],
        "scenes": [
            {
                "id": s.id, "scene_number": s.scene_number, "location": s.location, "description": s.description,
                "dialogue": s.dialogue, "timing": s.timing, "audio_url": _url(s.audio_path),
                "cast": [{"character": c.character.name, "position": c.position, "looks_at": c.looks_at,
                          "action": c.action, "emotion": c.emotion, "speaks": c.speaks} for c in s.cast],
                "shots": [
                    {
                        "id": sh.id, "shot_number": sh.shot_number, "status": sh.status, "camera": sh.camera,
                        "framing": sh.framing, "movement": sh.movement, "duration": sh.duration_seconds,
                        "prompt": sh.prompt, "keyframe_prompt": sh.keyframe_prompt,
                        "negative_prompt": sh.negative_prompt, "keyframe_url": _url(sh.keyframe_path),
                        "video_url": _url(sh.video_path), "used_fallback": sh.used_fallback,
                        "versions": [{"version": v.version_number, "model": v.model_used, "status": v.status,
                                      "qa_passed": v.qa_passed, "qa_notes": v.qa_notes, "error": v.error_reason,
                                      "video_url": _url(v.video_path)} for v in sh.versions],
                    }
                    for sh in s.shots
                ],
            }
            for s in j.scenes
        ],
    }


@router.post("/jobs/{job_id}/approve")
def approve(job_id: str, req: ReviewRequest, db: Session = Depends(get_db)):
    j = _job_or_404(db, job_id)
    if not j.video_path:
        raise HTTPException(409, "no video to approve yet")
    j.review_status, j.review_notes, j.status = "approved", req.notes, "done"
    db.commit()
    return {"approved": True, "delivery": deliver(job_id)}


@router.post("/jobs/{job_id}/reject")
def reject(job_id: str, req: ReviewRequest, db: Session = Depends(get_db)):
    j = _job_or_404(db, job_id)
    j.review_status, j.review_notes = "rejected", req.notes
    db.commit()
    return {"rejected": True}


@router.post("/shots/{shot_id}/regenerate")
def regenerate_shot(shot_id: str, req: RegenerateShotRequest, db: Session = Depends(get_db)):
    shot = db.get(Shot, shot_id)
    if shot is None:
        raise HTTPException(404, "shot not found")
    for field in ("prompt", "keyframe_prompt", "negative_prompt"):
        if getattr(req, field):
            setattr(shot, field, getattr(req, field))
    shot.status, shot.retry_count, shot.keyframe_path, shot.used_fallback = "pending", 0, None, False
    job = shot.scene.job
    job.status, job.review_status = "generating_shots", "pending"
    db.commit()
    return {"queued": True, "runner": dispatch("reshoot", job.id)}


@router.post("/jobs/{job_id}/reassemble")
def reassemble(job_id: str, db: Session = Depends(get_db)):
    _job_or_404(db, job_id)
    return {"queued": True, "runner": dispatch("reassemble", job_id)}


@router.post("/jobs/{job_id}/rerun")
def rerun(job_id: str, db: Session = Depends(get_db)):
    j = _job_or_404(db, job_id)
    j.status, j.review_status, j.updated_at = "queued", "pending", datetime.now(timezone.utc)
    db.commit()
    return {"queued": True, "runner": dispatch("pipeline", job_id)}
