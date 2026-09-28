"""Email the originating recruiter when a candidate replies by SMS."""
from __future__ import annotations

from html import escape
import logging
import re
from datetime import datetime, timezone

import httpx

from . import config


logger = logging.getLogger("medhunt.sms_reply_email")
_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def configured(recruiter_email: str = "") -> bool:
    recipients = [*config.SMS_REPLY_NOTIFICATION_EMAILS, str(recruiter_email or "").casefold()]
    return bool(
        config.SENDGRID_API_KEY and _EMAIL.fullmatch(config.EMAIL_FROM)
        and any(_EMAIL.fullmatch(item) for item in recipients)
    )


def send_reply_email(*, conversation: dict, reply: str, original: str) -> bool:
    recipients = list(config.SMS_REPLY_NOTIFICATION_EMAILS)
    recruiter_email = str(conversation.get("initiated_by_email") or "").strip().casefold()
    if _EMAIL.fullmatch(recruiter_email) and recruiter_email not in recipients:
        recipients.append(recruiter_email)
    recipients = [item for item in recipients if _EMAIL.fullmatch(item)]
    if not recipients or not config.SENDGRID_API_KEY or not _EMAIL.fullmatch(config.EMAIL_FROM):
        logger.error("Candidate reply email is not configured.")
        return False
    candidate = str(conversation.get("candidate_name") or "Candidate")
    phone = str(conversation.get("candidate_phone") or "")
    received = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    rows = (
        ("Candidate", candidate), ("Phone", phone), ("Received", received),
        ("Original outreach", original or "Unavailable"),
        ("Candidate reply", reply.strip() or "[empty message]"),
    )
    table = "".join(
        "<tr><th align='left' style='padding:6px 12px 6px 0'>"
        f"{escape(label)}</th><td style='padding:6px 0;white-space:pre-wrap'>"
        f"{escape(value)}</td></tr>" for label, value in rows
    )
    payload = {
        "personalizations": [{"to": [{"email": email} for email in recipients]}],
        "from": {"email": config.EMAIL_FROM, "name": config.EMAIL_FROM_NAME},
        "subject": f"[Candidate reply] {candidate}",
        "content": [{"type": "text/html", "value": (
            "<p>A candidate replied to SMS outreach.</p><table>" + table + "</table>"
        )}],
    }
    try:
        response = httpx.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={"Authorization": f"Bearer {config.SENDGRID_API_KEY}"},
            json=payload, timeout=config.SENDGRID_TIMEOUT,
        )
        if 200 <= response.status_code < 300:
            return True
        logger.error("Candidate reply email failed with HTTP %s.", response.status_code)
    except httpx.HTTPError as exc:
        logger.error("Candidate reply email failed (%s).", type(exc).__name__)
    return False
