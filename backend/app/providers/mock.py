"""Free, local, no-API-key providers. The video one is also the last-resort fallback when every
real generation attempt fails: it animates the keyframe with a slow Ken Burns zoom so the viewer
still gets motion rather than a frozen slide."""

import subprocess
import textwrap
import wave

from PIL import Image, ImageDraw, ImageFont

from app.config import get_settings
from app.providers.base import ImageProvider, AudioProvider, VideoProvider, GenerationError


class MockImageProvider(ImageProvider):
    def generate_subject_image(self, prompt, out_path, width=768, height=768, seed=None):
        img = Image.new("RGB", (width, height), color=(30, 30, 40))
        draw = ImageDraw.Draw(img)
        font = ImageFont.load_default()
        wrapped = "\n".join(textwrap.wrap(prompt[:300], width=30))
        draw.multiline_text((40, height // 3), wrapped, fill=(230, 230, 230), font=font, spacing=6)
        img.save(out_path)
        return out_path


class MockAudioProvider(AudioProvider):
    def generate_tts(self, script: str, out_path: str, voice: str | None = None) -> str:
        duration_seconds = max(1, min(20, len(script) // 15))
        framerate = 22050
        with wave.open(out_path, "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(framerate)
            wf.writeframes(b"\x00\x00" * duration_seconds * framerate)
        return out_path


class MockVideoProvider(VideoProvider):
    name = "local_kenburns"

    def generate_video(self, image_path, script, duration_seconds, out_path, model=None, negative_prompt=""):
        w, h = get_settings().frame_size
        fps = 24
        frames = int(duration_seconds * fps)
        vf = (
            f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2},"
            f"zoompan=z='min(zoom+0.0015,1.25)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={frames}:s={w}x{h}:fps={fps},format=yuv420p"
        )
        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-i", image_path,
            "-vf", vf, "-t", str(duration_seconds), "-c:v", "libx264", "-an", out_path,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        except FileNotFoundError as exc:
            raise GenerationError("ffmpeg not installed") from exc
        except subprocess.TimeoutExpired as exc:
            raise GenerationError("local render timed out", kind="timeout") from exc
        if result.returncode != 0:
            raise GenerationError(f"ffmpeg failed: {result.stderr[-500:]}")
        return out_path
