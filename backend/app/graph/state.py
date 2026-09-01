from typing import TypedDict


class GraphState(TypedDict, total=False):
    job_id: str
    lead_id: str
    raw_prompt: str

    industry: str
    topic: str

    script: str
    subject_image_path: str
    audio_path: str
    video_path: str

    attempt_count: int
    max_attempts: int
    used_fallback: bool

    status: str
    error: str
