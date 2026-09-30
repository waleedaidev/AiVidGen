from pydantic import BaseModel


class StartRequest(BaseModel):
    prompt: str


class StartResponse(BaseModel):
    lead_id: str
    job_id: str
    first_message: str


class ChatTurnRequest(BaseModel):
    lead_id: str
    message: str


class ChatTurnResponse(BaseModel):
    reply: str
    done: bool
    awaiting_video: bool = False


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: int
    used_fallback: bool
    video_url: str | None = None
    upsell_message: str | None = None


class ReviewRequest(BaseModel):
    notes: str | None = None


class RegenerateShotRequest(BaseModel):
    prompt: str | None = None
    keyframe_prompt: str | None = None
    negative_prompt: str | None = None
