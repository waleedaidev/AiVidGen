from abc import ABC, abstractmethod


class GenerationError(Exception):
    """Raised by a provider when generation fails (bad output, API error, timeout).
    `kind` lets the retry loop pick a repair strategy (e.g. rewrite the prompt on nsfw)."""

    def __init__(self, message: str, kind: str = "error"):
        super().__init__(message)
        self.kind = kind


class ImageProvider(ABC):
    @abstractmethod
    def generate_subject_image(
        self, prompt: str, out_path: str, width: int = 768, height: int = 768, seed: int | None = None
    ) -> str:
        """Generate an image and save it to out_path. Returns out_path."""


class AudioProvider(ABC):
    @abstractmethod
    def generate_tts(self, script: str, out_path: str, voice: str | None = None) -> str:
        """Generate a voiceover (wav) for script and save it to out_path. Returns out_path."""


class VideoProvider(ABC):
    name = "base"

    @abstractmethod
    def generate_video(
        self,
        image_path: str,
        script: str,
        duration_seconds: int,
        out_path: str,
        model: str | None = None,
        negative_prompt: str = "",
    ) -> str:
        """Animate a keyframe image into a clip following the prompt `script`, save to out_path.
        Raises GenerationError on failure so the caller can retry/fallback."""
