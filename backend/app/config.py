import os
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    provider_mode: str = "free"  # "mock" (fully local/fake) | "free" (Pollinations/Piper/HF) | "live" (Highfield)

    database_url: str = "postgresql+psycopg://aividgen:aividgen@localhost:5432/aividgen"

    openrouter_api_key: str = ""
    openrouter_chat_model: str = "openai/gpt-4o-mini"

    highfield_api_key: str = ""
    highfield_base_url: str = ""

    huggingface_api_token: str = ""
    huggingface_video_model: str = "damo-vilab/text-to-video-ms-1.7b"

    piper_voice_model_path: str = ""

    pexels_api_key: str = ""
    unsplash_access_key: str = ""

    max_generation_attempts: int = 2
    chat_max_turns: int = 10

    storage_dir: str = "storage"

    @property
    def storage_dir_abs(self) -> str:
        return self.storage_dir if os.path.isabs(self.storage_dir) else os.path.join(_BACKEND_DIR, self.storage_dir)


@lru_cache
def get_settings() -> Settings:
    return Settings()
