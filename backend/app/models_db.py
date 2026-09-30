import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, Boolean, DateTime, Text, ForeignKey, Float, JSON
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
    __tablename__ = "generation_jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    status: Mapped[str] = mapped_column(String, default="queued")
    # queued | analyzing_brief | writing_script | extracting_characters | generating_references
    # | generating_audio | planning_scenes | mapping_interactions | planning_shots | building_prompts
    # | generating_shots | assembling | awaiting_review | done | failed

    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    used_fallback: Mapped[bool] = mapped_column(Boolean, default=False)

    brief: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    script: Mapped[str | None] = mapped_column(Text, nullable=True)
    full_script: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    subject_image_path: Mapped[str | None] = mapped_column(String, nullable=True)
    audio_path: Mapped[str | None] = mapped_column(String, nullable=True)
    video_path: Mapped[str | None] = mapped_column(String, nullable=True)

    review_status: Mapped[str] = mapped_column(String, default="pending")  # pending | approved | rejected
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivery_log: Mapped[str | None] = mapped_column(Text, nullable=True)

    error_log: Mapped[str | None] = mapped_column(Text, nullable=True)

    lead: Mapped["Lead"] = relationship(back_populates="jobs")
    characters: Mapped[list["Character"]] = relationship(back_populates="job", order_by="Character.created_at")
    scenes: Mapped[list["Scene"]] = relationship(back_populates="job", order_by="Scene.scene_number")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    role: Mapped[str] = mapped_column(String)  # user | assistant
    content: Mapped[str] = mapped_column(Text)

    lead: Mapped["Lead"] = relationship(back_populates="messages")


class StockClip(Base):
    """Pre-fetched Pexels/Unsplash clips, tagged by industry."""

    __tablename__ = "stock_clips"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    industry_tag: Mapped[str] = mapped_column(String, index=True)
    source: Mapped[str] = mapped_column(String)  # pexels | unsplash
    file_path: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Character(Base):
    """Character registry: one locked identity reused in every scene/shot prompt."""

    __tablename__ = "characters"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(ForeignKey("generation_jobs.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    key: Mapped[str] = mapped_column(String)  # short stable id used by the script, e.g. "A"
    name: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String, default="support")
    appearance: Mapped[str] = mapped_column(Text, default="")
    personality: Mapped[str] = mapped_column(Text, default="")
    voice: Mapped[str] = mapped_column(String, default="neutral")
    seed: Mapped[int] = mapped_column(Integer, default=0)
    reference_image_path: Mapped[str | None] = mapped_column(String, nullable=True)

    job: Mapped["GenerationJob"] = relationship(back_populates="characters")


class Scene(Base):
    __tablename__ = "scenes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(ForeignKey("generation_jobs.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    scene_number: Mapped[int] = mapped_column(Integer)
    location: Mapped[str] = mapped_column(String, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    dialogue: Mapped[list | None] = mapped_column(JSON, nullable=True)  # [{speaker, text, emotion}]
    audio_path: Mapped[str | None] = mapped_column(String, nullable=True)
    audio_duration: Mapped[float] = mapped_column(Float, default=0.0)
    timing: Mapped[list | None] = mapped_column(JSON, nullable=True)  # [{speaker, start, end, text}]

    job: Mapped["GenerationJob"] = relationship(back_populates="scenes")
    cast: Mapped[list["SceneCharacter"]] = relationship(back_populates="scene", cascade="all, delete-orphan")
    shots: Mapped[list["Shot"]] = relationship(
        back_populates="scene", order_by="Shot.shot_number", cascade="all, delete-orphan"
    )


class SceneCharacter(Base):
    """Who is in the scene and what they're doing: blocking, gaze, action, emotion."""

    __tablename__ = "scene_characters"

    scene_id: Mapped[str] = mapped_column(ForeignKey("scenes.id"), primary_key=True)
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), primary_key=True)
    speaks: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[str] = mapped_column(String, default="center")
    looks_at: Mapped[str | None] = mapped_column(String, nullable=True)
    action: Mapped[str] = mapped_column(Text, default="")
    emotion: Mapped[str] = mapped_column(String, default="neutral")

    scene: Mapped["Scene"] = relationship(back_populates="cast")
    character: Mapped["Character"] = relationship()


class Shot(Base):
    __tablename__ = "shots"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    scene_id: Mapped[str] = mapped_column(ForeignKey("scenes.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    shot_number: Mapped[int] = mapped_column(Integer)
    camera: Mapped[str] = mapped_column(String, default="eye-level")
    framing: Mapped[str] = mapped_column(String, default="medium shot")
    movement: Mapped[str] = mapped_column(String, default="slow push-in")
    action: Mapped[str] = mapped_column(Text, default="")
    duration_seconds: Mapped[int] = mapped_column(Integer, default=6)

    prompt: Mapped[str] = mapped_column(Text, default="")
    keyframe_prompt: Mapped[str] = mapped_column(Text, default="")
    negative_prompt: Mapped[str] = mapped_column(Text, default="")
    keyframe_path: Mapped[str | None] = mapped_column(String, nullable=True)

    status: Mapped[str] = mapped_column(String, default="pending")  # pending | generating | done | failed
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    video_path: Mapped[str | None] = mapped_column(String, nullable=True)
    used_fallback: Mapped[bool] = mapped_column(Boolean, default=False)

    scene: Mapped["Scene"] = relationship(back_populates="shots")
    versions: Mapped[list["VideoVersion"]] = relationship(
        back_populates="shot", order_by="VideoVersion.version_number", cascade="all, delete-orphan"
    )


class VideoVersion(Base):
    """Every generation attempt of a shot, so retries/regenerations are auditable."""

    __tablename__ = "video_versions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    shot_id: Mapped[str] = mapped_column(ForeignKey("shots.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    version_number: Mapped[int] = mapped_column(Integer)
    model_used: Mapped[str] = mapped_column(String)
    prompt_used: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending | done | failed
    video_path: Mapped[str | None] = mapped_column(String, nullable=True)
    qa_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    qa_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    shot: Mapped["Shot"] = relationship(back_populates="versions")
