"""Pollinations.ai image provider — genuinely free, unlimited, no API key or signup required.
Unlike most "free tier" services (credit caps, watermarks, trial periods), this one has none
of that, so it's the default real image provider until Highfield's image endpoint is wired up.
"""

import urllib.parse

import httpx

from app.providers.base import ImageProvider, GenerationError

POLLINATIONS_URL = "https://image.pollinations.ai/prompt/{prompt}"


class PollinationsImageProvider(ImageProvider):
    def generate_subject_image(self, prompt: str, out_path: str) -> str:
        encoded = urllib.parse.quote(prompt)
        url = POLLINATIONS_URL.format(prompt=encoded)
        try:
            resp = httpx.get(url, params={"width": 768, "height": 768, "nologo": "true"}, timeout=60)
        except httpx.HTTPError as exc:
            raise GenerationError(f"Pollinations request failed: {exc}") from exc

        if resp.status_code != 200 or "image" not in resp.headers.get("content-type", ""):
            raise GenerationError(f"Pollinations returned unexpected response: {resp.status_code}")

        with open(out_path, "wb") as f:
            f.write(resp.content)
        return out_path
