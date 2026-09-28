"""Small server-side Twilio SMS client and webhook signature verifier."""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
from urllib.parse import quote

import httpx

from . import config


class TwilioSmsError(RuntimeError):
    pass


def enabled() -> bool:
    return bool(config.TWILIO_SMS_ENABLED)


def normalize_phone(value: str) -> str:
    raw = str(value or "").strip()
    digits = re.sub(r"\D", "", raw)
    if raw.startswith("+") and 8 <= len(digits) <= 15:
        return "+" + digits
    if config.DEFAULT_PHONE_COUNTRY.casefold() == "us":
        if len(digits) == 10:
            return "+1" + digits
        if len(digits) == 11 and digits.startswith("1"):
            return "+" + digits
    raise TwilioSmsError("The candidate mobile number is not a valid E.164 phone number.")


def send_sms(to_number: str, message: str, *, status_callback: str = "") -> dict:
    if not enabled():
        raise TwilioSmsError("Twilio SMS is not configured.")
    url = (
        "https://api.twilio.com/2010-04-01/Accounts/"
        f"{quote(config.TWILIO_ACCOUNT_SID, safe='')}/Messages.json"
    )
    payload = {
        "To": normalize_phone(to_number),
        "From": config.TWILIO_PHONE_NUMBER,
        "Body": str(message),
    }
    if status_callback:
        payload["StatusCallback"] = status_callback
    try:
        response = httpx.post(
            url, data=payload,
            auth=(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN),
            timeout=config.TWILIO_SMS_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise TwilioSmsError(f"Twilio SMS request failed ({type(exc).__name__}).") from exc
    if response.status_code >= 400:
        try:
            detail = response.json().get("message") or response.text
        except Exception:
            detail = response.text
        raise TwilioSmsError(f"Twilio SMS failed ({response.status_code}): {detail}"[:1000])
    try:
        result = response.json()
    except ValueError as exc:
        raise TwilioSmsError("Twilio returned an invalid response.") from exc
    return dict(result) if isinstance(result, dict) else {}


def validate_webhook(url: str, form: dict[str, list[str]], signature: str) -> bool:
    """Validate Twilio's X-Twilio-Signature for form-encoded webhooks."""
    if not config.TWILIO_AUTH_TOKEN or not url or not signature:
        return False
    signed = str(url)
    for key in sorted(form):
        values = form[key] if isinstance(form[key], list) else [form[key]]
        for value in sorted(str(item) for item in values):
            signed += str(key) + value
    digest = hmac.new(
        config.TWILIO_AUTH_TOKEN.encode(), signed.encode(), hashlib.sha1,
    ).digest()
    expected = base64.b64encode(digest).decode()
    return hmac.compare_digest(expected, str(signature))
