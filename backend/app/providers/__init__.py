from app.config import get_settings
from app.providers.base import ImageProvider, AudioProvider, VideoProvider, GenerationError
from app.providers.mock import MockImageProvider, MockAudioProvider, MockVideoProvider
from app.providers.highfield import HighfieldImageProvider, HighfieldAudioProvider, HighfieldVideoProvider
from app.providers.pollinations import PollinationsImageProvider
from app.providers.piper_tts import PiperAudioProvider
from app.providers.huggingface_video import HuggingFaceVideoProvider


def get_image_provider() -> ImageProvider:
    settings = get_settings()
    if settings.provider_mode == "live" and settings.highfield_api_key:
        return HighfieldImageProvider()
    if settings.provider_mode == "mock":
        return MockImageProvider()
    # Free, unlimited, no key required — the default "real" image provider.
    return PollinationsImageProvider()


def get_audio_provider() -> AudioProvider:
    settings = get_settings()
    if settings.provider_mode == "live" and settings.highfield_api_key:
        return HighfieldAudioProvider()
    if settings.provider_mode == "mock":
        return MockAudioProvider()
    try:
        return PiperAudioProvider()
    except GenerationError:
        # No voice model configured yet — fall back to the silent placeholder rather than crash.
        return MockAudioProvider()


def get_video_provider() -> VideoProvider:
    settings = get_settings()
    if settings.provider_mode == "live" and settings.highfield_api_key:
        return HighfieldVideoProvider()
    if settings.provider_mode == "mock":
        return MockVideoProvider()
    try:
        return HuggingFaceVideoProvider()
    except GenerationError:
        # No HF token configured yet — fall back to the ffmpeg placeholder rather than crash.
        return MockVideoProvider()
