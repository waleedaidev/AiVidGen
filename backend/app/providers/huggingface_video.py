"""Hugging Face Serverless Inference API video provider — free, but a real free API (not a
paid trial), so expect occasional cold-start failures (model "loading") and rate limits. Those
surface as GenerationError, which feeds straight into the existing retry -> stock-fallback path,
so a flaky free tier is fine here by design.

Needs a free token from https://huggingface.co/settings/tokens (no payment info required).

Note: the default model (damo-vilab/text-to-video-ms-1.7b) is text-to-video only — it ignores
the subject reference image. Swap HUGGINGFACE_VIDEO_MODEL for an image-to-video model later if
visual consistency with the subject image becomes a priority.
"""

import httpx

from app.config import get_settings
from app.providers.base import VideoProvider, GenerationError

HF_INFERENCE_URL = "https://api-inference.huggingface.co/models/{model}"


class HuggingFaceVideoProvider(VideoProvider):
    def __init__(self):
        settings = get_settings()
        self.token = settings.huggingface_api_token
        self.model = settings.huggingface_video_model
        if not self.token:
            raise GenerationError("HUGGINGFACE_API_TOKEN not set")

    def generate_video(self, image_path: str, script: str, duration_seconds: int, out_path: str) -> str:
        url = HF_INFERENCE_URL.format(model=self.model)
        try:
            resp = httpx.post(
                url,
                headers={"Authorization": f"Bearer {self.token}"},
                json={"inputs": script},
                timeout=120,
            )
        except httpx.HTTPError as exc:
            raise GenerationError(f"Hugging Face request failed: {exc}") from exc

        if resp.status_code == 503:
            # Model is cold-loading. Treat as a normal generation failure so the graph's
            # existing retry logic handles it (a retry a few seconds later often succeeds).
            raise GenerationError(f"Hugging Face model is loading: {resp.text[:200]}")

        content_type = resp.headers.get("content-type", "")
        if resp.status_code != 200 or ("video" not in content_type and "octet-stream" not in content_type):
            raise GenerationError(f"Hugging Face video gen failed ({resp.status_code}): {resp.text[:300]}")

        with open(out_path, "wb") as f:
            f.write(resp.content)
        return out_path
