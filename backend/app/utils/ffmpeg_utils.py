import json
import os
import subprocess
import wave

from app.providers.base import GenerationError

AUDIO_RATE = 22050


def _run(cmd: list[str], timeout: int = 300, what: str = "ffmpeg") -> None:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise GenerationError(f"{cmd[0]} not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise GenerationError(f"{what} timed out", kind="timeout") from exc
    if result.returncode != 0:
        raise GenerationError(f"{what} failed: {result.stderr[-600:]}")


def probe(path: str) -> dict:
    """{'duration': float, 'has_video': bool, 'width': int, 'height': int} — empty dict if unreadable."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
            capture_output=True, text=True, timeout=30,
        )
        data = json.loads(result.stdout or "{}")
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return {}
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    return {
        "duration": float(data.get("format", {}).get("duration") or 0),
        "has_video": video is not None,
        "width": int(video.get("width", 0)) if video else 0,
        "height": int(video.get("height", 0)) if video else 0,
    }


def wav_duration(path: str) -> float:
    with wave.open(path, "rb") as wf:
        return wf.getnframes() / float(wf.getframerate())


def build_scene_audio(line_wavs: list[tuple[str, str, str]], out_path: str, gap: float = 0.35) -> tuple[float, list[dict]]:
    """Concatenate dialogue line wavs (speaker, text, path) with small gaps into one mono wav.
    Returns (total_duration, timestamps)."""
    timing, cursor = [], 0.0
    with wave.open(out_path, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(AUDIO_RATE)
        silence = b"\x00\x00" * int(AUDIO_RATE * gap)
        for speaker, text, path in line_wavs:
            resampled = path + ".norm.wav"
            _run(["ffmpeg", "-y", "-i", path, "-ac", "1", "-ar", str(AUDIO_RATE), "-sample_fmt", "s16", resampled], what="audio resample")
            with wave.open(resampled, "rb") as wf:
                frames = wf.readframes(wf.getnframes())
                dur = wf.getnframes() / float(wf.getframerate())
            os.remove(resampled)
            out.writeframes(frames)
            timing.append({"speaker": speaker, "text": text, "start": round(cursor, 2), "end": round(cursor + dur, 2)})
            cursor += dur
            out.writeframes(silence)
            cursor += gap
    return cursor, timing


def normalize_clip(src: str, out_path: str, width: int, height: int, duration: float, fade: float = 0.3) -> str:
    """Scale/crop to the target frame, fixed fps, exact duration, fade in/out (the transition)."""
    fade_out_start = max(0.0, duration - fade)
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},fps=24,"
        f"tpad=stop_mode=clone:stop_duration={duration},"
        f"fade=t=in:st=0:d={fade},fade=t=out:st={fade_out_start:.2f}:d={fade},format=yuv420p"
    )
    _run(
        ["ffmpeg", "-y", "-i", src, "-vf", vf, "-t", f"{duration:.2f}", "-an", "-c:v", "libx264", "-preset", "veryfast", out_path],
        what="clip normalize",
    )
    return out_path


def concat_clips(clips: list[str], out_path: str) -> str:
    list_file = out_path + ".txt"
    with open(list_file, "w", encoding="utf-8") as f:
        for c in clips:
            f.write(f"file '{os.path.abspath(c).replace(os.sep, '/')}'\n")
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file, "-c", "copy", out_path], what="concat")
    os.remove(list_file)
    return out_path


def fit_audio(src: str | None, out_path: str, duration: float) -> str:
    """Pad with silence / trim so the scene's narration exactly matches its video length."""
    if src:
        cmd = ["ffmpeg", "-y", "-i", src, "-af", "apad", "-t", f"{duration:.2f}", "-ac", "1", "-ar", str(AUDIO_RATE), out_path]
    else:
        cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r={AUDIO_RATE}:cl=mono", "-t", f"{duration:.2f}", out_path]
    _run(cmd, what="audio fit")
    return out_path


def concat_audio(parts: list[str], out_path: str) -> str:
    inputs = []
    for p in parts:
        inputs += ["-i", p]
    filt = "".join(f"[{i}:a]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=0:a=1[a]"
    _run(["ffmpeg", "-y", *inputs, "-filter_complex", filt, "-map", "[a]", out_path], what="audio concat")
    return out_path


def mux_final(video: str, narration: str, out_path: str, music: str | None = None, music_volume: float = 0.12) -> str:
    if music:
        cmd = [
            "ffmpeg", "-y", "-i", video, "-i", narration, "-stream_loop", "-1", "-i", music,
            "-filter_complex",
            f"[2:a]volume={music_volume}[m];[1:a][m]amix=inputs=2:duration=first:dropout_transition=0[a]",
            "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-shortest", out_path,
        ]
    else:
        cmd = ["ffmpeg", "-y", "-i", video, "-i", narration, "-map", "0:v", "-map", "1:a",
               "-c:v", "copy", "-c:a", "aac", "-shortest", out_path]
    _run(cmd, what="final mux")
    return out_path
