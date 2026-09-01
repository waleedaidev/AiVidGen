"""Real Highfield-backed providers.

NOT WIRED UP YET. We don't have Highfield's REST endpoint spec (base URL, auth header shape,
request/response schema) yet. Once that's shared, fill in the three TODOs below — the
generate_image/generate_video/generate_audio graph nodes don't need to change at all, since
they only depend on the ImageProvider/AudioProvider/VideoProvider interface.

Until HIGHFIELD_API_KEY + HIGHFIELD_BASE_URL are set and PROVIDER_MODE=live, these classes are
never instantiated (see app/providers/__init__.py) — mock providers run instead.
"""

import httpx

from app.config import get_settings
from app.providers.base import ImageProvider, AudioProvider, VideoProvider, GenerationError


class _HighfieldClient:
    def __init__(self):
        settings = get_settings()
        self.base_url = settings.highfield_base_url
        self.api_key = settings.highfield_api_key
        self.client = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=120,
        )


class HighfieldImageProvider(ImageProvider, _HighfieldClient):
    def __init__(self):
        _HighfieldClient.__init__(self)

    def generate_subject_image(self, prompt: str, out_path: str) -> str:
        # TODO: call Highfield's image-generation endpoint once its API spec is known.
        raise GenerationError("HighfieldImageProvider not implemented yet")


class HighfieldAudioProvider(AudioProvider, _HighfieldClient):
    def __init__(self):
        _HighfieldClient.__init__(self)

    def generate_tts(self, script: str, out_path: str) -> str:
        # TODO: call Highfield's TTS/voice endpoint once its API spec is known.
        raise GenerationError("HighfieldAudioProvider not implemented yet")


class HighfieldVideoProvider(VideoProvider, _HighfieldClient):
    def __init__(self):
        _HighfieldClient.__init__(self)

    def generate_video(self, image_path: str, script: str, duration_seconds: int, out_path: str) -> str:
        # TODO: call Highfield's video-generation endpoint once its API spec is known.
        raise GenerationError("HighfieldVideoProvider not implemented yet")
