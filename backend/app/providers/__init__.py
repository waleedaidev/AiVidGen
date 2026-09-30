from app.config import get_settings
from app.providers.base import ImageProvider, AudioProvider, VideoProvider, GenerationError
from app.providers.mock import MockImageProvider, MockAudioProvider, MockVideoProvider
from app.providers.highfield import HighfieldImageProvider, HighfieldVideoProvider
from app.providers.pollinations import PollinationsImageProvider
from app.providers.piper_tts import PiperAudioProvider


def _highfield_ready() -> bool:
    s = get_settings()
    return bool(s.highfield_api_key_id and s.highfield_api_key_secret)


class FallbackImageProvider(ImageProvider):
    """Try each provider in order; the first success wins."""

    def __init__(self, *providers: ImageProvider):
        self.providers = providers

    def generate_subject_image(self, prompt, out_path, width=768, height=768, seed=None):
        errors = []
        for provider in self.providers:
            try:
                return provider.generate_subject_image(prompt, out_path, width=width, height=height, seed=seed)
            except GenerationError as exc:
                errors.append(f"{type(provider).__name__}: {exc}")
        raise GenerationError(" | ".join(errors))


def get_image_provider() -> ImageProvider:
    settings = get_settings()
    if settings.provider_mode == "mock":
        return MockImageProvider()
    if settings.provider_mode == "live" and settings.image_provider == "higgsfield" and _highfield_ready():
        return FallbackImageProvider(HighfieldImageProvider(), PollinationsImageProvider())
    return PollinationsImageProvider()


def get_audio_provider() -> AudioProvider:
    if get_settings().provider_mode == "mock":
        return MockAudioProvider()
    try:
        return PiperAudioProvider()
    except GenerationError:
        return MockAudioProvider()


def get_video_provider() -> VideoProvider:
    if get_settings().provider_mode == "live" and _highfield_ready():
        return HighfieldVideoProvider()
    return MockVideoProvider()
