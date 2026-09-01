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
    used_fallback: bool
    video_url: str | None = None
