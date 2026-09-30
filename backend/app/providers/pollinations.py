"""Pollinations.ai image provider — free, no API key. Used for character reference images and
per-shot keyframes. A fixed seed per character keeps faces/outfits more consistent."""

import urllib.parse

import httpx

from app.providers.base import ImageProvider, GenerationError

POLLINATIONS_URL = "https://image.pollinations.ai/prompt/{prompt}"


class PollinationsImageProvider(ImageProvider):
    def generate_subject_image(self, prompt, out_path, width=768, height=768, seed=None):
        url = POLLINATIONS_URL.format(prompt=urllib.parse.quote(prompt[:1500]))
        params = {"width": width, "height": height, "nologo": "true", "model": "flux"}
        if seed is not None:
            params["seed"] = seed
        try:
            resp = httpx.get(url, params=params, timeout=120, follow_redirects=True)
        except httpx.HTTPError as exc:
            raise GenerationError(f"Pollinations request failed: {exc}") from exc

        if resp.status_code != 200 or "image" not in resp.headers.get("content-type", ""):
            raise GenerationError(f"Pollinations returned unexpected response: {resp.status_code}")

        with open(out_path, "wb") as f:
            f.write(resp.content)
        return out_path
