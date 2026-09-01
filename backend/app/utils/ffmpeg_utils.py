import subprocess

from app.providers.base import GenerationError


def overlay_audio_on_video(video_path: str, audio_path: str, out_path: str, duration_seconds: int) -> str:
    """Used by the fallback path: takes a stock clip + our generated voiceover and produces
    a single trimmed mp4, so a fallback video still carries the personalized script/voice."""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-map", "0:v:0", "-map", "1:a:0",
        "-t", str(duration_seconds),
        "-c:v", "libx264", "-c:a", "aac",
        "-shortest",
        out_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except FileNotFoundError as exc:
        raise GenerationError("ffmpeg not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise GenerationError("fallback assembly timed out") from exc
    if result.returncode != 0:
        raise GenerationError(f"ffmpeg overlay failed: {result.stderr[-500:]}")
    return out_path
