import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Lead(Base):
    """One row per landing-page visitor. Saved incrementally as the chat progresses
    so a dropped-off visitor is still a usable lead for the sales team."""

    __tablename__ = "leads"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    raw_prompt: Mapped[str] = mapped_column(Text)
    industry: Mapped[str | None] = mapped_column(String, nullable=True)
    topic: Mapped[str | None] = mapped_column(String, nullable=True)

    business_type: Mapped[str | None] = mapped_column(String, nullable=True)
    tone: Mapped[str | None] = mapped_column(String, nullable=True)
    target_audience: Mapped[str | None] = mapped_column(String, nullable=True)
    use_case: Mapped[str | None] = mapped_column(String, nullable=True)
    preferred_style: Mapped[str | None] = mapped_column(String, nullable=True)

    email: Mapped[str | None] = mapped_column(String, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)

    chat_status: Mapped[str] = mapped_column(String, default="in_progress")
    # in_progress | email_captured | completed | dropped_off

    jobs: Mapped[list["GenerationJob"]] = relationship(back_populates="lead")
    messages: Mapped[list["ChatMessage"]] = relationship(back_populates="lead")


class GenerationJob(Base):
    """One background video-generation job, fired the moment the landing prompt
    is submitted, running in parallel with the chat."""

    __tablename__ = "generation_jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    status: Mapped[str] = mapped_column(String, default="queued")
    # queued | generating_script | generating_assets | generating_video
    # | assembling | done | failed

    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    used_fallback: Mapped[bool] = mapped_column(Boolean, default=False)

    script: Mapped[str | None] = mapped_column(Text, nullable=True)
    subject_image_path: Mapped[str | None] = mapped_column(String, nullable=True)
    audio_path: Mapped[str | None] = mapped_column(String, nullable=True)
    video_path: Mapped[str | None] = mapped_column(String, nullable=True)

    error_log: Mapped[str | None] = mapped_column(Text, nullable=True)

    lead: Mapped["Lead"] = relationship(back_populates="jobs")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    role: Mapped[str] = mapped_column(String)  # user | assistant
    content: Mapped[str] = mapped_column(Text)

    lead: Mapped["Lead"] = relationship(back_populates="messages")


class StockClip(Base):
    """Pre-fetched Pexels/Unsplash clips, tagged by industry, used as the
    retry-exhausted fallback so the user always gets *something*."""

    __tablename__ = "stock_clips"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    industry_tag: Mapped[str] = mapped_column(String, index=True)
    source: Mapped[str] = mapped_column(String)  # pexels | unsplash
    file_path: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
