import os

from app.config import get_settings
from app.db import SessionLocal
from app.graph.state import GraphState
from app.llm.openrouter_client import chat_completion_json, NoApiKeyError
from app.models_db import GenerationJob
from app.providers import get_image_provider, get_audio_provider, get_video_provider
from app.providers.base import GenerationError
from app.providers.stock_library import pick_fallback_clip
from app.utils.ffmpeg_utils import overlay_audio_on_video

TEASER_DURATION_SECONDS = 12

INDUSTRY_KEYWORDS = {
    "restaurant": ["restaurant", "cafe", "food", "menu", "dine"],
    "fitness": ["gym", "fitness", "workout", "trainer"],
    "real_estate": ["real estate", "property", "house", "apartment", "realtor"],
    "fashion": ["fashion", "clothing", "boutique", "apparel"],
    "salon": ["salon", "spa", "beauty", "haircut"],
    "retail": ["shop", "store", "retail", "ecommerce", "product"],
}


def _update_job(job_id: str, **fields):
    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if job is None:
            return
        for key, value in fields.items():
            setattr(job, key, value)
        db.commit()
    finally:
        db.close()


def _guess_industry(prompt: str) -> str | None:
    lowered = prompt.lower()
    for tag, keywords in INDUSTRY_KEYWORDS.items():
        if any(kw in lowered for kw in keywords):
            return tag
    return None


def parse_intent(state: GraphState) -> GraphState:
    _update_job(state["job_id"], status="parsing_intent")
    prompt = state["raw_prompt"]

    try:
        result = chat_completion_json(
            [
                {
                    "role": "system",
                    "content": (
                        "Extract structured info from a short video request. "
                        "Reply as JSON: {\"industry\": one of "
                        f"{list(INDUSTRY_KEYWORDS.keys())} or \"other\", \"topic\": short phrase}}."
                    ),
                },
                {"role": "user", "content": prompt},
            ]
        )
        industry = result.get("industry") or _guess_industry(prompt) or "other"
        topic = result.get("topic") or prompt[:80]
    except (NoApiKeyError, Exception):
        industry = _guess_industry(prompt) or "other"
        topic = prompt[:80]

    return {**state, "industry": industry, "topic": topic}


def generate_script(state: GraphState) -> GraphState:
    _update_job(state["job_id"], status="generating_script")
    prompt = state["raw_prompt"]

    try:
        result = chat_completion_json(
            [
                {
                    "role": "system",
                    "content": (
                        "Write a short (10-15 second) video voiceover script, 2-3 punchy sentences, "
                        "for the given business idea. Reply as JSON: {\"script\": \"...\"}."
                    ),
                },
                {"role": "user", "content": prompt},
            ]
        )
        script = result.get("script") or prompt
    except (NoApiKeyError, Exception):
        script = f"Introducing something new: {prompt}. See it in action, right now."

    _update_job(state["job_id"], script=script)
    return {**state, "script": script}


def generate_assets(state: GraphState) -> GraphState:
    """Subject image + TTS voiceover, done together (conceptually parallel; sequential here
    for simplicity since both are cheap/fast in mock mode and the real providers are async APIs
    that could be fanned out with asyncio.gather once wired to Highfield)."""
    _update_job(state["job_id"], status="generating_assets")
    settings = get_settings()
    job_dir = os.path.join(settings.storage_dir_abs, state["job_id"])
    os.makedirs(job_dir, exist_ok=True)

    image_path = os.path.join(job_dir, "subject.png")
    audio_path = os.path.join(job_dir, "voiceover.wav")

    get_image_provider().generate_subject_image(state["topic"], image_path)
    get_audio_provider().generate_tts(state["script"], audio_path)

    _update_job(state["job_id"], subject_image_path=image_path, audio_path=audio_path)
    return {**state, "subject_image_path": image_path, "audio_path": audio_path}


def generate_video(state: GraphState) -> GraphState:
    settings = get_settings()
    job_dir = os.path.join(settings.storage_dir_abs, state["job_id"])
    attempt = state.get("attempt_count", 0) + 1
    _update_job(state["job_id"], status="generating_video", attempt_count=attempt)

    out_path = os.path.join(job_dir, f"video_attempt{attempt}.mp4")
    try:
        get_video_provider().generate_video(
            state["subject_image_path"], state["script"], TEASER_DURATION_SECONDS, out_path
        )
        _update_job(state["job_id"], video_path=out_path, status="done")
        return {**state, "video_path": out_path, "attempt_count": attempt, "status": "done"}
    except GenerationError as exc:
        _update_job(state["job_id"], error_log=str(exc))
        return {**state, "attempt_count": attempt, "status": "failed", "error": str(exc)}


def should_retry(state: GraphState) -> str:
    max_attempts = state.get("max_attempts", 2)
    if state.get("status") == "done":
        return "done"
    if state.get("attempt_count", 0) < max_attempts:
        return "retry"
    return "fallback"


def fallback_stock(state: GraphState) -> GraphState:
    _update_job(state["job_id"], status="using_fallback")
    settings = get_settings()
    job_dir = os.path.join(settings.storage_dir_abs, state["job_id"])
    out_path = os.path.join(job_dir, "video_fallback.mp4")

    db = SessionLocal()
    try:
        clip = pick_fallback_clip(db, state.get("industry"))
    finally:
        db.close()

    if clip is None:
        # No stock library seeded at all — nothing to fall back to.
        _update_job(state["job_id"], status="failed", error_log="generation failed, no stock fallback available")
        return {**state, "status": "failed"}

    try:
        overlay_audio_on_video(clip.file_path, state["audio_path"], out_path, TEASER_DURATION_SECONDS)
    except GenerationError:
        # Even the overlay failed (e.g. no ffmpeg) — hand back the raw stock clip, silent.
        out_path = clip.file_path

    _update_job(state["job_id"], status="done", used_fallback=True, video_path=out_path)
    return {**state, "video_path": out_path, "used_fallback": True, "status": "done"}
