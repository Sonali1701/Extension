"""Retry extension analytics events until Halo records them."""
from __future__ import annotations

import hashlib
import logging
import threading
from datetime import datetime, timezone

import httpx

from . import config, healthboard_auth, store

_log = logging.getLogger("medhunt.analytics_delivery")
_stop = threading.Event()
_thread: threading.Thread | None = None


def event_key(event: dict) -> str:
    identity = f"{event['auth0_sub']}|{event['id']}|{event['created']}"
    return hashlib.sha256(identity.encode()).hexdigest()[:32]


def deliver(event: dict, *, token: str = "") -> bool:
    platform = str(event.get("platform") or "").strip().lower()
    provider = str(event.get("provider") or "").strip().lower()
    payload = {
        "event_id": event_key(event),
        "candidate_id": int(event["candidate_id"]),
        "status": str(event.get("status") or "unknown"),
        "source": platform or "unknown",
        "platform": platform or "unknown",
        "provider": provider,
        "run_id": str(event.get("run_id") or ""),
        "occurred_at": datetime.fromtimestamp(
            float(event["created"]), timezone.utc,
        ).isoformat(),
    }
    if token:
        delivered = healthboard_auth.report_enrichment(token, **payload)
    else:
        delivered = healthboard_auth.report_enrichment_service(
            user_id=str(event["auth0_sub"]), **payload,
        )
    if delivered:
        store.mark_halo_enrichment_delivered(int(event["id"]))
    return bool(delivered)


def flush_pending(limit: int = 50) -> int:
    if not healthboard_auth.enabled() or not config.MEDHUNT_HEALTHBOARD_SERVICE_TOKEN:
        return 0
    sent = 0
    for event in store.pending_halo_enrichment_events(limit):
        try:
            if deliver(event):
                sent += 1
        except Exception as exc:
            _log.warning("Halo analytics replay failed (%s).", type(exc).__name__)
            if not (isinstance(exc, httpx.HTTPStatusError)
                    and exc.response.status_code in {404, 422}):
                break
    return sent


def _run() -> None:
    while not _stop.is_set():
        try:
            flush_pending()
        except Exception as exc:
            _log.warning("Halo analytics delivery cycle failed (%s).", type(exc).__name__)
        _stop.wait(30)


def start() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    if not healthboard_auth.enabled() or not config.MEDHUNT_HEALTHBOARD_SERVICE_TOKEN:
        return
    _stop.clear()
    _thread = threading.Thread(target=_run, name="medhunt-analytics-delivery", daemon=True)
    _thread.start()


def stop() -> None:
    global _thread
    _stop.set()
    if _thread:
        _thread.join(timeout=5)
    _thread = None
