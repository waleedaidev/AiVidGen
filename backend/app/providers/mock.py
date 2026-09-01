"""Free, local, no-API-key providers. Used whenever PROVIDER_MODE=mock (the default) so the
whole pipeline is runnable and testable before any paid keys exist.

Video generation deliberately calls ffmpeg directly (image + silence -> short mp4) instead of
faking success, so the retry/fallback path can be exercised for real: if ffmpeg isn't installed,
generate_video raises GenerationError exactly like a real provider outage would.
"""

import subprocess
import textwrap
import wave

from PIL import Image, ImageDraw, ImageFont

from app.providers.base import ImageProvider, AudioProvider, VideoProvider, GenerationError


class MockImageProvider(ImageProvider):
    def generate_subject_image(self, prompt: str, out_path: str) -> str:
        img = Image.new("RGB", (768, 768), color=(30, 30, 40))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None
        wrapped = "\n".join(textwrap.wrap(prompt, width=30))
        draw.multiline_text((40, 320), wrapped, fill=(230, 230, 230), font=font, spacing=6)
        img.save(out_path)
        return out_path


class MockAudioProvider(AudioProvider):
    def generate_tts(self, script: str, out_path: str) -> str:
        # Silent placeholder track, duration scales with script length so timing still lines up.
        duration_seconds = max(3, min(20, len(script) // 15))
        framerate = 22050
        n_frames = duration_seconds * framerate
        with wave.open(out_path, "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(framerate)
            wf.writeframes(b"\x00\x00" * n_frames)
        return out_path


class MockVideoProvider(VideoProvider):
    def generate_video(self, image_path: str, script: str, duration_seconds: int, out_path: str) -> str:
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", image_path,
            "-f", "lavfi", "-i", f"anullsrc=r=22050:cl=mono",
            "-t", str(duration_seconds),
            "-vf", "scale=768:768",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest",
            out_path,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except FileNotFoundError as exc:
            raise GenerationError("ffmpeg not installed") from exc
        except subprocess.TimeoutExpired as exc:
            raise GenerationError("mock video generation timed out") from exc
        if result.returncode != 0:
            raise GenerationError(f"ffmpeg failed: {result.stderr[-500:]}")
        return out_path
