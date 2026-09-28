"""Optional server-side email deliverability validation.

API credentials never reach the browser extension. Email checks are disabled
by default because verification may consume credits.
"""
from __future__ import annotations

import httpx

from . import config


def verify_email(email: str) -> dict:
    if not config.VERIFY_EMAILS or not config.NEVERBOUNCE_API_KEY:
        return {"deliverability": "not_checked"}
    try:
        response = httpx.post(
            "https://api.neverbounce.com/v4.2/single/check",
            params={
                "key": config.NEVERBOUNCE_API_KEY,
                "email": email,
                "timeout": 10,
            },
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "success":
            return {"deliverability": "unknown", "service": "neverbounce"}
        return {
            "deliverability": str(payload.get("result") or "unknown"),
            "flags": payload.get("flags") or [],
            "service": "neverbounce",
        }
    except Exception as error:  # noqa: BLE001
        return {
            "deliverability": "unknown",
            "service": "neverbounce",
            "error": f"{type(error).__name__}: {error}",
        }
