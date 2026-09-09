"""Hugging Face Inference Providers router — video provider.

IMPORTANT (verified live, 2026-09): the free `hf-inference` provider currently has ZERO
video-generation models available — every text-to-video / image-to-video model on the Hub
that supports serverless inference routes through paid third-party providers (fal, novita,
replicate, etc.), not the free tier. So as things stand, every call here will raise
GenerationError and fall through to the stock/local fallback — that's not a bug, it's the
current state of HF's free tier. Left wired up (rather than removed) so it starts working
automatically the moment HF adds a free video model, or if you point HUGGINGFACE_VIDEO_MODEL
at a model you have a paid Inference Provider arrangement for.

Needs a free token from https://huggingface.co/settings/tokens (no payment info required).
"""

import httpx

from app.config import get_settings
from app.providers.base import VideoProvider, GenerationError

HF_INFERENCE_URL = "https://router.huggingface.co/hf-inference/models/{model}"


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
