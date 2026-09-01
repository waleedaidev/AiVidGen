from app.config import get_settings
from app.providers.base import ImageProvider, AudioProvider, VideoProvider
from app.providers.mock import MockImageProvider, MockAudioProvider, MockVideoProvider
from app.providers.highfield import HighfieldImageProvider, HighfieldAudioProvider, HighfieldVideoProvider


def get_image_provider() -> ImageProvider:
    settings = get_settings()
    if settings.provider_mode == "live" and settings.highfield_api_key:
        return HighfieldImageProvider()
    return MockImageProvider()


def get_audio_provider() -> AudioProvider:
    settings = get_settings()
    if settings.provider_mode == "live" and settings.highfield_api_key:
        return HighfieldAudioProvider()
    return MockAudioProvider()


def get_video_provider() -> VideoProvider:
    settings = get_settings()
    if settings.provider_mode == "live" and settings.highfield_api_key:
        return HighfieldVideoProvider()
    return MockVideoProvider()
