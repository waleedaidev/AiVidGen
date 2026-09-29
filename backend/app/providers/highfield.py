"""Highfield-backed providers using cheapest models for cost optimization.

Highfield API uses an async request model:
1. Submit request (POST) → get request_id
2. Poll status (GET) → wait for completion
3. Download results

Cost-optimized model selection:
- Image: z_image (Tongyi-MAI, Chinese, super-fast, budget-friendly)
- Video: minimax_h3_max (MiniMax, Chinese, fast, 5-15 sec clips)
- Audio: Piper (local, no cost)
"""

import httpx
import time
import uuid
from pathlib import Path

from app.config import get_settings
from app.providers.base import ImageProvider, AudioProvider, VideoProvider, GenerationError


class HighfieldClient:
    """Base Highfield API client with auth and polling."""

    def __init__(self):
        settings = get_settings()
        self.api_key_id = settings.highfield_api_key_id
        self.api_key_secret = settings.highfield_api_key_secret
        self.base_url = "https://api.higgsfield.ai"

        if not self.api_key_id or not self.api_key_secret:
            raise GenerationError("HIGHFIELD_API_KEY_ID and HIGHFIELD_API_KEY_SECRET not set")

    def _auth_header(self) -> str:
        """Format authorization header."""
        return f"Key {self.api_key_id}:{self.api_key_secret}"

    def _submit_request(self, endpoint: str, payload: dict) -> str:
        """Submit generation request and return request_id."""
        idempotency_key = str(uuid.uuid4()).lower()

        with httpx.Client() as client:
            resp = client.post(
                f"{self.base_url}{endpoint}",
                headers={
                    "Authorization": self._auth_header(),
                    "Content-Type": "application/json",
                    "Idempotency-Key": idempotency_key,
                },
                json=payload,
                timeout=30,
            )

        if resp.status_code != 200:
            raise GenerationError(f"Highfield request failed ({resp.status_code}): {resp.text}")

        data = resp.json()
        request_id = data.get("request_id")
        if not request_id:
            raise GenerationError(f"No request_id in response: {data}")

        return request_id

    def _poll_status(self, request_id: str, timeout_sec: int = 300) -> dict:
        """Poll request status until completion or timeout."""
        start = time.time()

        while time.time() - start < timeout_sec:
            with httpx.Client() as client:
                resp = client.get(
                    f"{self.base_url}/requests/{request_id}/status",
                    headers={"Authorization": self._auth_header()},
                    timeout=30,
                )

            if resp.status_code != 200:
                raise GenerationError(f"Status check failed ({resp.status_code}): {resp.text}")

            data = resp.json()
            status = data.get("status")

            if status == "completed":
                return data
            elif status in ("failed", "nsfw", "canceled"):
                raise GenerationError(f"Generation failed with status '{status}'")
            elif status == "queued" or status == "processing":
                time.sleep(5)  # Poll every 5 seconds
            else:
                raise GenerationError(f"Unknown status: {status}")

        raise GenerationError(f"Generation timeout after {timeout_sec}s")

    def _download_file(self, url: str, out_path: str) -> str:
        """Download file from URL."""
        with httpx.stream("GET", url) as resp:
            if resp.status_code != 200:
                raise GenerationError(f"Download failed ({resp.status_code})")

            Path(out_path).parent.mkdir(parents=True, exist_ok=True)
            with open(out_path, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=8192):
                    f.write(chunk)

        return out_path


class HighfieldImageProvider(ImageProvider, HighfieldClient):
    """Generate images using z_image (Tongyi-MAI, cheapest Chinese model)."""

    def __init__(self):
        HighfieldClient.__init__(self)

    def generate_subject_image(self, prompt: str, out_path: str) -> str:
        """Generate subject reference image using z_image (super-fast, budget-friendly)."""
        request_id = self._submit_request(
            "/higgsfield-ai/generate/image",
            {
                "model": "z_image",
                "prompt": prompt,
            },
        )

        result = self._poll_status(request_id)
        images = result.get("images", [])

        if not images:
            raise GenerationError("No images in response")

        image_url = images[0].get("url")
        if not image_url:
            raise GenerationError("No image URL in response")

        return self._download_file(image_url, out_path)


class HighfieldVideoProvider(VideoProvider, HighfieldClient):
    """Generate videos using minimax_h3_max (MiniMax, cheapest Chinese model)."""

    def __init__(self):
        HighfieldClient.__init__(self)

    def generate_video(self, image_path: str, script: str, duration_seconds: int, out_path: str) -> str:
        """Generate video from image/script using minimax_h3_max (fast, budget-friendly, 5-15 sec)."""
        request_id = self._submit_request(
            "/higgsfield-ai/generate/video",
            {
                "model": "minimax_h3_max",
                "prompt": script,
                "duration": min(duration_seconds, 15),  # MiniMax H3 Max supports 5-15s
                "start_image_path": image_path,
                "resolution": "768p",  # Balanced cost/quality
            },
        )

        result = self._poll_status(request_id, timeout_sec=600)  # 10 min timeout for video
        videos = result.get("videos", [])

        if not videos:
            raise GenerationError("No videos in response")

        video_url = videos[0].get("url")
        if not video_url:
            raise GenerationError("No video URL in response")

        return self._download_file(video_url, out_path)


class HighfieldAudioProvider(AudioProvider, HighfieldClient):
    """Generate audio/TTS using Highfield's API (when endpoint documented)."""

    def __init__(self):
        HighfieldClient.__init__(self)

    def generate_tts(self, script: str, out_path: str) -> str:
        """Generate text-to-speech audio."""
        # Highfield TTS endpoint not yet documented in quickstart
        # Placeholder: would be similar async pattern
        raise GenerationError("HighfieldAudioProvider not documented yet — use Piper for now")
