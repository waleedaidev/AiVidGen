"""Delivery: email (SendGrid) + WhatsApp (Twilio). Each channel is skipped and logged when its keys
or the lead's contact detail are missing. Idempotent: a delivered job is never sent twice."""

import logging
import os
from datetime import datetime, timezone

import httpx

from app.config import get_settings
from app.db import SessionLocal
from app.models_db import GenerationJob

log = logging.getLogger("aividgen.delivery")


def storage_url(path: str | None) -> str | None:
    if not path:
        return None
    rel = os.path.relpath(path, get_settings().storage_dir_abs).replace(os.sep, "/")
    return None if rel.startswith("..") else f"/storage/{rel}"


def video_url(job: GenerationJob) -> str | None:
    return storage_url(job.video_path)


def _send_email(to: str, link: str, title: str) -> str:
    s = get_settings()
    if not (s.sendgrid_api_key and s.sendgrid_from_email):
        return "email: skipped (SendGrid not configured)"
    body = (
        f"Hi! Your video preview is ready: {link}\n\n"
        "This is a short teaser. Reply to this email or wait for our team to reach out "
        "to unlock the full-length video and more variations."
    )
    resp = httpx.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers={"Authorization": f"Bearer {s.sendgrid_api_key}"},
        json={
            "personalizations": [{"to": [{"email": to}]}],
            "from": {"email": s.sendgrid_from_email},
            "subject": f"Your video is ready: {title}",
            "content": [{"type": "text/plain", "value": body}],
        },
        timeout=30,
    )
    return f"email: {'sent' if resp.status_code < 300 else f'failed {resp.status_code} {resp.text[:200]}'}"


def _send_whatsapp(to: str, link: str) -> str:
    s = get_settings()
    if not (s.twilio_account_sid and s.twilio_auth_token and s.twilio_whatsapp_from):
        return "whatsapp: skipped (Twilio not configured)"
    data = {
        "From": f"whatsapp:{s.twilio_whatsapp_from}",
        "To": f"whatsapp:{to.replace(' ', '').replace('-', '')}",
        "Body": f"Your video teaser is ready! {link}\nWant the full video? Reply here and an agent will contact you.",
    }
    if not any(h in link for h in ("localhost", "127.0.0.1")):
        data["MediaUrl"] = link
    resp = httpx.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{s.twilio_account_sid}/Messages.json",
        auth=(s.twilio_account_sid, s.twilio_auth_token),
        data=data,
        timeout=30,
    )
    return f"whatsapp: {'sent' if resp.status_code < 300 else f'failed {resp.status_code} {resp.text[:200]}'}"


def deliver(job_id: str) -> str:
    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if job is None or job.delivered_at or job.status != "done":
            return "not deliverable"
        lead = job.lead
        if not (lead.email or lead.phone):
            return "waiting for contact details"
        link = get_settings().public_base_url.rstrip("/") + (video_url(job) or "")
        title = (job.brief or {}).get("title", "your video")
        results = []
        for contact, sender in ((lead.email, lambda: _send_email(lead.email, link, title)),
                                (lead.phone, lambda: _send_whatsapp(lead.phone, link))):
            if not contact:
                continue
            try:
                results.append(sender())
            except httpx.HTTPError as exc:
                results.append(f"error: {exc}")
        job.delivery_log = "\n".join(results)
        if any(r.endswith("sent") for r in results):
            job.delivered_at = datetime.now(timezone.utc)
        db.commit()
        log.info("delivery for %s: %s", job_id, job.delivery_log)
        return job.delivery_log
    finally:
        db.close()
