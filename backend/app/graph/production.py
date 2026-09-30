"""Production stages 9-11: model router + parallel shot generation, QA with prompt-repair retry
loop, and final FFmpeg assembly. All DB-driven, so the editor's "regenerate shot" reuses them."""

import os
import re
from concurrent.futures import ThreadPoolExecutor

from app.config import get_settings
from app.graph.common import session, job_dir, set_status, llm_json, log
from app.graph.planning import pick_music
from app.graph.state import GraphState
from app.models_db import Character, GenerationJob, Scene, SceneCharacter, Shot, VideoVersion
from app.providers import get_image_provider, get_video_provider
from app.providers.base import GenerationError
from app.providers.mock import MockImageProvider, MockVideoProvider
from app.providers.stock_library import pick_fallback_clip
from app.utils import ffmpeg_utils as ff
from app.utils.model_router import models_for_attempt

ACTIVE = ("pending", "retry")


def _job_shots(db, job_id: str, statuses: tuple[str, ...] | None = None) -> list[Shot]:
    q = db.query(Shot).join(Scene).filter(Scene.job_id == job_id)
    if statuses:
        q = q.filter(Shot.status.in_(statuses))
    return q.order_by(Scene.scene_number, Shot.shot_number).all()


# 9. MODEL ROUTER + VIDEO GENERATION ----------------------------------------------------------

def _ensure_keyframe(db, shot: Shot, out_dir: str) -> str:
    if shot.keyframe_path and os.path.exists(shot.keyframe_path):
        return shot.keyframe_path
    w, h = get_settings().frame_size
    lead_char = (
        db.query(Character).join(SceneCharacter, SceneCharacter.character_id == Character.id)
        .filter(SceneCharacter.scene_id == shot.scene_id).first()
    )
    out = os.path.join(out_dir, f"keyframe_s{shot.scene.scene_number}_{shot.shot_number}_{shot.retry_count}.jpg")
    try:
        get_image_provider().generate_subject_image(
            shot.keyframe_prompt, out, width=w, height=h, seed=lead_char.seed if lead_char else None
        )
    except GenerationError as exc:
        log.warning("keyframe failed for shot %s (%s); using placeholder", shot.id, exc)
        MockImageProvider().generate_subject_image(shot.keyframe_prompt, out, width=w, height=h)
    shot.keyframe_path = out
    return out


def _produce_shot(shot_id: str) -> None:
    with session() as db:
        shot = db.get(Shot, shot_id)
        job_id = shot.scene.job_id
        keyframe = _ensure_keyframe(db, shot, job_dir(job_id, "keyframes"))
        provider = get_video_provider()
        model = models_for_attempt(shot.retry_count) if provider.name == "higgsfield" else provider.name
        version = VideoVersion(
            shot_id=shot.id, version_number=len(shot.versions) + 1, model_used=model, prompt_used=shot.prompt
        )
        shot.versions.append(version)
        shot.status = "generating"
        db.flush()
        prompt, negative, duration = shot.prompt, shot.negative_prompt, shot.duration_seconds
        out = os.path.join(job_dir(job_id, "shots"), f"shot_{shot.scene.scene_number}_{shot.shot_number}_v{version.version_number}.mp4")
        version_id = version.id

    try:
        provider.generate_video(keyframe, prompt, duration, out, model=model, negative_prompt=negative)
        status, error = "generated", None
    except GenerationError as exc:
        status, error = "gen_failed", f"{exc.kind}: {exc}"
        log.warning("shot %s generation failed: %s", shot_id, error)

    with session() as db:
        shot, version = db.get(Shot, shot_id), db.get(VideoVersion, version_id)
        shot.status = status
        version.status = "done" if status == "generated" else "failed"
        version.error_reason = error
        if status == "generated":
            version.video_path = out
            shot.video_path = out


def generate_shots(state: GraphState) -> GraphState:
    set_status(state["job_id"], "generating_shots")
    with session() as db:
        ids = [s.id for s in _job_shots(db, state["job_id"], ACTIVE)]
    with ThreadPoolExecutor(max_workers=get_settings().shot_concurrency) as pool:
        list(pool.map(_produce_shot, ids))
    return {"stage": "generate_shots"}


# 10. QA (technical; VLM check intentionally skipped) + RETRY ROUTING -------------------------

def technical_qa(path: str | None, expected_seconds: int) -> tuple[bool, str]:
    if not path or not os.path.exists(path):
        return False, "file missing"
    if os.path.getsize(path) < 30_000:
        return False, "file too small / empty render"
    info = ff.probe(path)
    if not info.get("has_video"):
        return False, "no video stream"
    if info["duration"] < min(2.0, expected_seconds * 0.5):
        return False, f"too short ({info['duration']:.1f}s)"
    return True, f"ok {info['width']}x{info['height']} {info['duration']:.1f}s"


def _last_resort(db, shot: Shot, industry: str | None) -> bool:
    """Retries exhausted: industry stock clip if the library has one, else animate the keyframe locally."""
    out = os.path.join(job_dir(shot.scene.job_id, "shots"), f"shot_{shot.scene.scene_number}_{shot.shot_number}_fallback.mp4")
    clip = pick_fallback_clip(db, industry)
    if clip and os.path.exists(clip.file_path):
        shot.video_path, model = clip.file_path, f"stock:{clip.source}"
    else:
        try:
            MockVideoProvider().generate_video(shot.keyframe_path, shot.prompt, shot.duration_seconds, out)
        except GenerationError as exc:
            log.error("local fallback failed for shot %s: %s", shot.id, exc)
            return False
        shot.video_path, model = out, "local_kenburns"
    shot.versions.append(VideoVersion(
        shot_id=shot.id, version_number=len(shot.versions) + 1, model_used=model,
        prompt_used=shot.prompt, status="done", video_path=shot.video_path, qa_passed=True, qa_notes="fallback",
    ))
    shot.used_fallback = True
    return True


def qa_check(state: GraphState) -> GraphState:
    set_status(state["job_id"], "quality_check")
    max_retries = get_settings().shot_max_retries
    with session() as db:
        industry = (db.get(GenerationJob, state["job_id"]).brief or {}).get("industry")
        for shot in _job_shots(db, state["job_id"], ("generated", "gen_failed")):
            version = shot.versions[-1]
            passed, notes = (False, version.error_reason or "generation failed")
            if shot.status == "generated":
                passed, notes = technical_qa(shot.video_path, shot.duration_seconds)
                version.qa_passed, version.qa_notes = passed, notes
            if passed:
                shot.status = "approved"
            elif shot.retry_count < max_retries and not notes.startswith("no_credits"):
                shot.status = "retry"
            else:
                shot.status = "approved" if _last_resort(db, shot, industry) else "failed"
        retry = bool(_job_shots(db, state["job_id"], ("retry",)))
    return {"route": "repair" if retry else "assemble"}


def route_after_qa(state: GraphState) -> str:
    return state.get("route", "assemble")


_RISKY = re.compile(r"\b(blood|gun|weapon|kill|sexy|nude|naked|violent|fight|drunk|lingerie|bikini)\w*", re.I)


def repair_prompts(state: GraphState) -> GraphState:
    """Prompt repair: rewrite on moderation/validation rejections, tighten on bad renders,
    keep as-is for transient network/timeouts. A new keyframe is drawn for every retry."""
    set_status(state["job_id"], "repairing_prompts")
    with session() as db:
        for shot in _job_shots(db, state["job_id"], ("retry",)):
            last = shot.versions[-1]
            reason = (last.error_reason or last.qa_notes or "").lower()
            shot.retry_count += 1
            shot.keyframe_path = None
            if reason.startswith(("nsfw", "rejected")):
                fixed = llm_json(
                    "Rewrite this video-generation prompt so it passes strict content moderation and API "
                    "validation: remove anything suggestive, violent or brand-infringing, keep the same scene, "
                    'people and camera, under 900 characters. Reply as JSON: {"prompt": str, "keyframe_prompt": str}',
                    f"Error: {reason}\nVideo prompt: {shot.prompt}\nKeyframe prompt: {shot.keyframe_prompt}",
                    temperature=0.3,
                ) or {}
                shot.prompt = fixed.get("prompt") or _RISKY.sub("", shot.prompt)[:900]
                shot.keyframe_prompt = fixed.get("keyframe_prompt") or _RISKY.sub("", shot.keyframe_prompt)[:900]
            elif not reason.startswith(("timeout", "network")) and "stable" not in shot.prompt:
                shot.prompt = f"{shot.prompt} Stable composition, minimal motion, no morphing."
            shot.status = "retry"
    return {"stage": "repair_prompts"}


# 11. FINAL ASSEMBLY --------------------------------------------------------------------------

def assemble(state: GraphState) -> GraphState:
    job_id = state["job_id"]
    set_status(job_id, "assembling")
    settings = get_settings()
    w, h = settings.frame_size
    work = job_dir(job_id, "assembly")

    with session() as db:
        job = db.get(GenerationJob, job_id)
        scenes = db.query(Scene).filter(Scene.job_id == job_id).order_by(Scene.scene_number).all()
        clips, narration = [], []
        for scene in scenes:
            shots = [s for s in scene.shots if s.status == "approved" and s.video_path]
            if not shots:
                continue
            if scene.audio_duration:
                scene_len = scene.audio_duration + 0.4
            else:
                scene_len = min(sum(s.duration_seconds for s in shots), 5.0 * len(shots))
            cut = scene_len / len(shots)
            for s in shots:
                clips.append(ff.normalize_clip(s.video_path, os.path.join(work, f"n_{scene.scene_number}_{s.shot_number}.mp4"), w, h, cut))
            narration.append(ff.fit_audio(scene.audio_path, os.path.join(work, f"a_{scene.scene_number}.wav"), scene_len))

        if not clips:
            raise GenerationError("no usable shots to assemble")

        video = ff.concat_clips(clips, os.path.join(work, "video.mp4"))
        voice = ff.concat_audio(narration, os.path.join(work, "narration.wav"))
        final = ff.mux_final(video, voice, os.path.join(job_dir(job_id), "final.mp4"),
                             music=pick_music((job.brief or {}).get("tone", "")))

        first = next((s for sc in scenes for s in sc.shots if s.keyframe_path), None)
        job.video_path = final
        job.audio_path = voice
        job.subject_image_path = first.keyframe_path if first else None
        job.used_fallback = any(s.used_fallback for sc in scenes for s in sc.shots)
        job.status = "awaiting_review" if settings.require_human_review else "done"
        job.review_status = "pending"
        status = job.status

    if status == "done":
        from app.delivery import deliver

        deliver(job_id)
    return {"stage": "assemble"}
