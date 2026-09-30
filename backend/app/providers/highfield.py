"""Higgsfield platform API (https://docs.higgsfield.ai).

Lifecycle (verified against the live API): POST /{model path} -> {request_id} ->
GET /requests/{id}/status until completed|failed|nsfw|canceled -> download `video.url` / `images[].url`.
Image-to-video models take a public `image_url`, so local keyframes are first pushed through
POST /files/generate-upload-url + a presigned PUT.
"""

import mimetypes
import time
import uuid
from pathlib import Path

import httpx

from app.config import get_settings
from app.providers.base import ImageProvider, VideoProvider, GenerationError
from app.utils.model_router import VIDEO_MODELS, snap_duration

BASE_URL = "https://api.higgsfield.ai"
TERMINAL_FAILURES = {"failed", "nsfw", "canceled"}


class HighfieldClient:
    def __init__(self):
        settings = get_settings()
        if not settings.highfield_api_key_id or not settings.highfield_api_key_secret:
            raise GenerationError("HIGHFIELD_API_KEY_ID / HIGHFIELD_API_KEY_SECRET not set")
        self._auth = f"Key {settings.highfield_api_key_id}:{settings.highfield_api_key_secret}"

    def submit(self, path: str, payload: dict) -> str:
        headers = {"Authorization": self._auth, "Idempotency-Key": str(uuid.uuid4())}
        try:
            resp = httpx.post(f"{BASE_URL}/{path}", headers=headers, json=payload, timeout=60)
        except httpx.HTTPError as exc:
            raise GenerationError(f"Higgsfield submit failed: {exc}", kind="network") from exc
        if resp.status_code >= 400:
            kind = "no_credits" if "not_enough_credits" in resp.text else "rejected"
            raise GenerationError(f"Higgsfield rejected request ({resp.status_code}): {resp.text[:300]}", kind=kind)
        request_id = resp.json().get("request_id")
        if not request_id:
            raise GenerationError(f"No request_id in response: {resp.text[:300]}")
        return request_id

    def wait(self, request_id: str, timeout_sec: int = 900) -> dict:
        deadline = time.time() + timeout_sec
        delay = 4
        while time.time() < deadline:
            try:
                resp = httpx.get(
                    f"{BASE_URL}/requests/{request_id}/status",
                    headers={"Authorization": self._auth},
                    timeout=30,
                )
            except httpx.HTTPError:
                time.sleep(delay)
                continue
            if resp.status_code >= 400:
                raise GenerationError(f"Status check failed ({resp.status_code}): {resp.text[:300]}")
            data = resp.json()
            status = data.get("status")
            if status == "completed":
                return data
            if status in TERMINAL_FAILURES:
                raise GenerationError(f"Generation ended as '{status}': {data.get('error')}", kind=status)
            time.sleep(delay)
            delay = min(delay + 2, 15)
        raise GenerationError(f"Generation timed out after {timeout_sec}s", kind="timeout")

    def upload(self, local_path: str) -> str:
        content_type = mimetypes.guess_type(local_path)[0] or "image/jpeg"
        resp = httpx.post(
            f"{BASE_URL}/files/generate-upload-url",
            headers={"Authorization": self._auth},
            json={"content_type": content_type},
            timeout=30,
        )
        if resp.status_code >= 400:
            raise GenerationError(f"Upload URL request failed ({resp.status_code}): {resp.text[:300]}")
        info = resp.json()
        headers = info.get("upload_headers") or {"Content-Type": content_type}
        with open(local_path, "rb") as f:
            put = httpx.put(info["upload_url"], content=f.read(), headers=headers, timeout=120)
        if put.status_code >= 400:
            raise GenerationError(f"File upload failed ({put.status_code}): {put.text[:300]}")
        return info["public_url"]

    @staticmethod
    def download(url: str, out_path: str) -> str:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        with httpx.stream("GET", url, timeout=300, follow_redirects=True) as resp:
            if resp.status_code != 200:
                raise GenerationError(f"Download failed ({resp.status_code})")
            with open(out_path, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=65536):
                    f.write(chunk)
        return out_path


class HighfieldImageProvider(ImageProvider):
    """Higgsfield Soul — the only image model exposed on the platform API. No seed parameter."""

    def __init__(self):
        self.client = HighfieldClient()

    def generate_subject_image(self, prompt, out_path, width=768, height=768, seed=None):
        aspect = "9:16" if height > width else "16:9" if width > height else "1:1"
        request_id = self.client.submit("higgsfield-ai/soul/standard", {"prompt": prompt, "aspect_ratio": aspect})
        images = self.client.wait(request_id, timeout_sec=300).get("images") or []
        if not images or not images[0].get("url"):
            raise GenerationError("No image URL in Higgsfield response")
        return self.client.download(images[0]["url"], out_path)


class HighfieldVideoProvider(VideoProvider):
    name = "higgsfield"

    def __init__(self):
        self.client = HighfieldClient()

    def generate_video(self, image_path, script, duration_seconds, out_path, model=None, negative_prompt=""):
        model_key = model or get_settings().video_model_primary
        spec = VIDEO_MODELS[model_key]
        payload = {
            "prompt": script[:2400],
            "image_url": self.client.upload(image_path),
            "duration": snap_duration(model_key, duration_seconds),
        }
        if spec.get("negative_prompt") and negative_prompt:
            payload["negative_prompt"] = negative_prompt[:1000]
        payload.update(spec.get("extra", {}))

        request_id = self.client.submit(spec["path"], payload)
        video = self.client.wait(request_id).get("video") or {}
        if not video.get("url"):
            raise GenerationError("No video URL in Higgsfield response")
        return self.client.download(video["url"], out_path)
