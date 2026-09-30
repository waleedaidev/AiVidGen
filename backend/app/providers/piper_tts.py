"""Piper TTS — local, offline, free. Uses the standalone piper binary (the `piper-tts` pip package
has no Windows/py3.12 wheel for its phonemizer). Voice models: https://huggingface.co/rhasspy/piper-voices

Characters get different voices: `voice` containing "male"/"female" picks PIPER_MALE_VOICE_PATH /
PIPER_FEMALE_VOICE_PATH, falling back to PIPER_VOICE_MODEL_PATH.
"""

import os
import subprocess

from app.config import get_settings
from app.providers.base import AudioProvider, GenerationError


class PiperAudioProvider(AudioProvider):
    def __init__(self):
        settings = get_settings()
        self.binary_path = settings.piper_binary_path
        self.default_model = settings.piper_voice_model_path
        self.voices = {
            "female": settings.piper_female_voice_path or self.default_model,
            "male": settings.piper_male_voice_path or self.default_model,
        }
        if not self.default_model or not os.path.exists(self.default_model):
            raise GenerationError("PIPER_VOICE_MODEL_PATH not set or file missing")

    def _model_for(self, voice: str | None) -> str:
        voice = (voice or "").lower()
        key = "female" if "female" in voice or "woman" in voice else "male" if "male" in voice or "man" in voice else None
        path = self.voices.get(key) if key else None
        return path if path and os.path.exists(path) else self.default_model

    def generate_tts(self, script: str, out_path: str, voice: str | None = None) -> str:
        cmd = [self.binary_path, "--model", self._model_for(voice), "--output_file", out_path]
        try:
            result = subprocess.run(cmd, input=script, capture_output=True, text=True, timeout=120)
        except FileNotFoundError as exc:
            raise GenerationError(f"piper binary not found at '{self.binary_path}'") from exc
        except subprocess.TimeoutExpired as exc:
            raise GenerationError("piper TTS timed out", kind="timeout") from exc
        if result.returncode != 0 or not os.path.exists(out_path):
            raise GenerationError(f"piper failed: {result.stderr[-500:]}")
        return out_path
