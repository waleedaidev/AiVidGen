"""Lead-qualification chat.

Looks like a free-form conversation (real LLM, gpt-4o-mini via OpenRouter, asks things like
"is this for your business?" to keep it engaging) but is really a guided slot-filling state
machine underneath: every turn extracts one required field and asks for the next one. This
keeps cost bounded (one cheap LLM call per turn, capped turn count) and guarantees we never
lose required lead data to a user going off-topic.

Slot order: business_type, tone -> [EMAIL GATE] -> target_audience, use_case, preferred_style
-> [PHONE GATE] -> done.

If OPENROUTER_API_KEY isn't set, falls back to a fully scripted question list (still works,
just not adaptive) so the app runs with zero keys.
"""

import re

from sqlalchemy.orm import Session

from app.config import get_settings
from app.llm.openrouter_client import chat_completion_json
from app.models_db import Lead, ChatMessage

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+?\d[\d\s\-]{7,}$")

SLOT_SEQUENCE = [
    "business_type",
    "tone",
    "email",
    "target_audience",
    "use_case",
    "preferred_style",
    "phone",
]

SLOT_PROMPTS = {
    "business_type": "Ask if this video is for their own business/brand, or a personal project.",
    "tone": "Ask what tone/vibe they want for the video (e.g. professional, fun, bold, elegant).",
    "email": "Ask for their email so you can send the video/preview to them.",
    "target_audience": "Ask who the video's target audience is (e.g. local customers, social media followers).",
    "use_case": "Ask where they plan to use the video (e.g. Instagram ad, website, WhatsApp status).",
    "preferred_style": "Ask if they prefer a more cinematic style or a fast/energetic style.",
    "phone": "Ask for their WhatsApp number so you can send them the finished video there.",
}

SCRIPTED_QUESTIONS = {
    "business_type": "Quick one first - is this video for your own business, or just a personal project?",
    "tone": "Got it. What tone should the video have - professional, fun, bold, or something else?",
    "email": "Nice, this is coming together. What's the best email to send your video to?",
    "target_audience": "Who's this video mainly for - your local customers, or a wider online audience?",
    "use_case": "Where will you mainly use it - Instagram/TikTok ads, your website, or WhatsApp status?",
    "preferred_style": "Last style question - more cinematic and slow, or fast and energetic?",
    "phone": "Almost done! What's your WhatsApp number so I can send the finished video there?",
}

GREETING = "Hey! I'm putting your video together right now in the background. While that renders, let's personalize it."


def _next_slot(lead: Lead) -> str | None:
    for slot in SLOT_SEQUENCE:
        if getattr(lead, slot) in (None, ""):
            return slot
    return None


def _validate(slot: str, value: str) -> bool:
    if slot == "email":
        return bool(EMAIL_RE.match(value.strip()))
    if slot == "phone":
        return bool(PHONE_RE.match(value.strip()))
    return bool(value.strip())


def _history_for_llm(lead: Lead, db: Session) -> list[dict]:
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.lead_id == lead.id)
        .order_by(ChatMessage.created_at)
        .all()
    )
    return [{"role": m.role, "content": m.content} for m in messages]


def _log(db: Session, lead: Lead, role: str, content: str):
    db.add(ChatMessage(lead_id=lead.id, role=role, content=content))
    db.commit()


def start_chat(lead: Lead, db: Session) -> str:
    settings = get_settings()
    first_slot = SLOT_SEQUENCE[0]

    if not settings.openrouter_api_key:
        opening = f"{GREETING} {SCRIPTED_QUESTIONS[first_slot]}"
    else:
        try:
            result = chat_completion_json(
                [
                    {
                        "role": "system",
                        "content": (
                            "You are a friendly assistant collecting details to personalize an AI-generated "
                            "video ad. Keep replies to 1-2 short sentences, warm and conversational, never robotic. "
                            f"Greet the user briefly (mention their video is rendering in the background), then: "
                            f"{SLOT_PROMPTS[first_slot]}. Reply as JSON: {{\"message\": \"...\"}}."
                        ),
                    },
                    {"role": "user", "content": lead.raw_prompt},
                ]
            )
            opening = result.get("message") or f"{GREETING} {SCRIPTED_QUESTIONS[first_slot]}"
        except Exception:
            opening = f"{GREETING} {SCRIPTED_QUESTIONS[first_slot]}"

    _log(db, lead, "assistant", opening)
    return opening


def handle_turn(lead: Lead, user_message: str, db: Session) -> tuple[str, bool]:
    """Returns (reply, done)."""
    settings = get_settings()
    _log(db, lead, "user", user_message)

    pending_slot = _next_slot(lead)
    if pending_slot is None:
        return "You're all set - your video is on its way!", True

    if not _validate(pending_slot, user_message):
        reask = f"Hmm, that doesn't look quite right. {SCRIPTED_QUESTIONS[pending_slot]}"
        _log(db, lead, "assistant", reask)
        return reask, False

    setattr(lead, pending_slot, user_message.strip())
    if pending_slot == "email":
        lead.chat_status = "email_captured"
    db.commit()

    next_slot = _next_slot(lead)
    if next_slot is None:
        lead.chat_status = "completed"
        db.commit()
        closing = (
            "Perfect, that's everything I need. Your teaser video will be ready any second - "
            "hang tight."
        )
        _log(db, lead, "assistant", closing)
        return closing, True

    if not settings.openrouter_api_key:
        reply = SCRIPTED_QUESTIONS[next_slot]
    else:
        try:
            history = _history_for_llm(lead, db)
            result = chat_completion_json(
                [
                    {
                        "role": "system",
                        "content": (
                            "You are a friendly assistant collecting details to personalize an AI-generated "
                            "video ad. Keep replies to 1-2 short sentences, conversational, never robotic. "
                            f"The user just answered the '{pending_slot}' question with: '{user_message}'. "
                            f"Briefly acknowledge it (reference their specific answer, e.g. their business type), "
                            f"then ask the next question: {SLOT_PROMPTS[next_slot]}. "
                            "Reply as JSON: {\"message\": \"...\"}."
                        ),
                    },
                    *history,
                ]
            )
            reply = result.get("message") or SCRIPTED_QUESTIONS[next_slot]
        except Exception:
            reply = SCRIPTED_QUESTIONS[next_slot]

    _log(db, lead, "assistant", reply)
    return reply, False
