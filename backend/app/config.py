import os
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # mock = everything local/fake | free = Pollinations + Piper + local render | live = Higgsfield video
    provider_mode: str = "free"

    database_url: str = "postgresql+psycopg://aividgen:aividgen@localhost:55490/aividgen"
    redis_url: str = "redis://localhost:56379/0"
    use_celery: bool = True

    openrouter_api_key: str = ""
    openrouter_chat_model: str = "deepseek/deepseek-v4-flash"

    highfield_api_key_id: str = ""
    highfield_api_key_secret: str = ""
    video_model_primary: str = "hailuo"
    video_model_fallback: str = "kling_turbo"
    image_provider: str = "higgsfield"  # higgsfield (Soul, live mode) | pollinations (free)

    piper_voice_model_path: str = ""
    piper_binary_path: str = "piper"
    piper_female_voice_path: str = ""
    piper_male_voice_path: str = ""

    pexels_api_key: str = ""
    unsplash_access_key: str = ""

    target_duration_seconds: int = 15
    max_shots: int = 3
    max_characters: int = 3
    shot_max_retries: int = 2
    shot_concurrency: int = 3
    aspect_ratio: str = "9:16"
    require_human_review: bool = False
    music_dir: str = "music"

    sendgrid_api_key: str = ""
    sendgrid_from_email: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = ""
    public_base_url: str = "http://localhost:8000"
    admin_token: str = ""

    max_generation_attempts: int = 2
    chat_max_turns: int = 10

    storage_dir: str = "storage"

    @property
    def storage_dir_abs(self) -> str:
        return self._abs(self.storage_dir)

    @property
    def music_dir_abs(self) -> str:
        return self._abs(self.music_dir)

    @staticmethod
    def _abs(path: str) -> str:
        return path if os.path.isabs(path) else os.path.join(_BACKEND_DIR, path)

    @property
    def frame_size(self) -> tuple[int, int]:
        return {"9:16": (720, 1280), "16:9": (1280, 720), "1:1": (1024, 1024)}.get(self.aspect_ratio, (720, 1280))


@lru_cache
def get_settings() -> Settings:
    return Settings()
