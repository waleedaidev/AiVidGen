"""Model router. Only Chinese budget video models, all verified to exist on api.higgsfield.ai.
Primary/fallback order comes from VIDEO_MODEL_PRIMARY / VIDEO_MODEL_FALLBACK."""

from app.config import get_settings

VIDEO_MODELS = {
    "hailuo_fast": {  # MiniMax Hailuo 2.3 Fast
        "path": "minimax/hailuo-2.3-fast/standard/image-to-video",
        "durations": [6, 10],
        "extra": {"prompt_optimizer": False},
    },
    "hailuo": {  # MiniMax Hailuo 2.3
        "path": "minimax/hailuo-2.3/standard/image-to-video",
        "durations": [6, 10],
        "extra": {"prompt_optimizer": False},
    },
    "kling_turbo": {  # Kling 2.5 Turbo (standard tier)
        "path": "kling-video/v2.5-turbo/standard/image-to-video",
        "durations": [5, 10],
        "negative_prompt": True,
    },
    "kling3_turbo": {  # Kling 3.0 Turbo, 720p
        "path": "kling-video/v3.0-turbo/image-to-video",
        "durations": list(range(3, 16)),
        "extra": {"resolution": "720p"},
    },
}


def snap_duration(model_key: str, seconds: int) -> int:
    """Round up to the nearest duration the model accepts (shortest billable clip that covers it)."""
    allowed = VIDEO_MODELS[model_key]["durations"]
    return next((d for d in allowed if d >= seconds), allowed[-1])


def allowed_durations() -> list[int]:
    return VIDEO_MODELS[get_settings().video_model_primary]["durations"]


def models_for_attempt(attempt: int) -> str:
    """Attempt 0 and 1 use the primary model; later attempts switch to the fallback model."""
    settings = get_settings()
    return settings.video_model_primary if attempt < 2 else settings.video_model_fallback
