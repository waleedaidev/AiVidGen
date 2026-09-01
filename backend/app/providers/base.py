from abc import ABC, abstractmethod


class GenerationError(Exception):
    """Raised by a provider when generation fails (bad output, API error, timeout).
    The graph's retry/fallback logic catches this."""


class ImageProvider(ABC):
    @abstractmethod
    def generate_subject_image(self, prompt: str, out_path: str) -> str:
        """Generate a subject/reference image and save it to out_path. Returns out_path."""


class AudioProvider(ABC):
    @abstractmethod
    def generate_tts(self, script: str, out_path: str) -> str:
        """Generate a voiceover for script and save it to out_path. Returns out_path."""


class VideoProvider(ABC):
    @abstractmethod
    def generate_video(self, image_path: str, script: str, duration_seconds: int, out_path: str) -> str:
        """Generate a short video clip from a reference image + script, save to out_path.
        Raises GenerationError on failure so the caller can retry/fallback."""
