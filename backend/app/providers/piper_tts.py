"""Piper TTS provider — local, offline, genuinely free/unlimited voice generation.

Requires:
  pip install piper-tts   (installs the `piper` CLI)
  a voice model: download a matching .onnx + .onnx.json pair from
  https://huggingface.co/rhasspy/piper-voices (e.g. en_US-lessac-medium.onnx)
  and set PIPER_VOICE_MODEL_PATH to the .onnx file's path.

Runs the official `piper` CLI via subprocess rather than the python bindings directly, since
the CLI interface is the stable, documented surface across piper-tts versions.
"""

import os
import subprocess

from app.config import get_settings
from app.providers.base import AudioProvider, GenerationError


class PiperAudioProvider(AudioProvider):
    def __init__(self):
        settings = get_settings()
        self.model_path = settings.piper_voice_model_path
        if not self.model_path or not os.path.exists(self.model_path):
            raise GenerationError(
                "PIPER_VOICE_MODEL_PATH not set or file missing — download a voice model from "
                "https://huggingface.co/rhasspy/piper-voices"
            )

    def generate_tts(self, script: str, out_path: str) -> str:
        cmd = ["piper", "--model", self.model_path, "--output_file", out_path]
        try:
            result = subprocess.run(cmd, input=script, capture_output=True, text=True, timeout=60)
        except FileNotFoundError as exc:
            raise GenerationError("piper CLI not found on PATH (pip install piper-tts)") from exc
        except subprocess.TimeoutExpired as exc:
            raise GenerationError("piper TTS timed out") from exc

        if result.returncode != 0:
            raise GenerationError(f"piper failed: {result.stderr[-500:]}")
        return out_path
