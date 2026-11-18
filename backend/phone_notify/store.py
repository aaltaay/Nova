"""The phone's notification settings and its subscribed phones, kept on the PC.

Owner: this module, the only reader and writer of ``phone-notify.json`` under the operator cache.
Shape: ``{schema_version: 1, settings: {...}, devices: [{id, endpoint, p256dh, auth, added_at}]}``
(``architecture/schema/desk-ops.md``, "Notifications to the phone").
Invalidation: a schema bump. A file with an unknown ``schema_version`` is refused loud and read as the
defaults (everything off, no phone), never guessed at; nothing else stales it. A phone leaves the list when
it unsubscribes, or when its push service says the address is gone (``sender``).

The file is read once and kept in memory (a fill asks on every fill, and waits for no disk); every write
goes through here and replaces what is kept. A hand edit of the file is read at the next backend start.

A phone's address and keys are what lets the PC notify it: they are not a login and open nothing on the PC.
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from phone_notify import webpush
from phone_notify.constants_phone_notify import (
    HOD_MODES,
    PHONE_NOTIFY_DEFAULT_SETTINGS,
    PHONE_NOTIFY_EARLIEST,
    PHONE_NOTIFY_ENDPOINT_MAX_CHARS,
    PHONE_NOTIFY_FILE,
    PHONE_NOTIFY_LATEST,
    PHONE_NOTIFY_MAX_DEVICES,
    PHONE_NOTIFY_PUSH_HOST_SUFFIXES,
    PHONE_NOTIFY_PUSH_HOSTS,
    PHONE_NOTIFY_SCHEMA_VERSION,
    PHONE_NOTIFY_STEP_MIN,
)

logger = logging.getLogger(__name__)
_lock = threading.RLock()
_SWITCHES = ("setups", "new_leader", "fills", "loss_limit")
# What was last read or written, and the file it belongs to (a test moves the cache folder).
_kept: tuple[Path, dict[str, Any]] | None = None


def path() -> Path:
    from paths import cache_dir

    return cache_dir() / PHONE_NOTIFY_FILE


def minutes_of(hhmm: Any) -> int | None:
    """Minutes past midnight of an ``"HH:MM"``; None when it is not one."""
    if not isinstance(hhmm, str) or len(hhmm) != 5 or hhmm[2] != ":":
        return None
    hours, minutes = hhmm[:2], hhmm[3:]
    if not (hours.isdigit() and minutes.isdigit()) or int(hours) > 23 or int(minutes) > 59:
        return None
    return int(hours) * 60 + int(minutes)


def normalize_settings(raw: Any) -> tuple[dict[str, Any] | None, str | None]:
    """The settings as kept, or why ``raw`` is not settings. Every field is required: a change sends the whole."""
    if not isinstance(raw, dict):
        return None, "The settings are not an object."
    if raw.get("hod_momo") not in HOD_MODES:
        return None, "HOD Momo is off, stars or all."
    for name in _SWITCHES:
        if not isinstance(raw.get(name), bool):
            return None, f"{name} is on or off."
    days = raw.get("days")
    if not isinstance(days, list) or any(isinstance(d, bool) or not isinstance(d, int) or not 0 <= d <= 6 for d in days):
        return None, "Days are numbers from 0 (Monday) to 6 (Sunday)."
    start, end = minutes_of(raw.get("start")), minutes_of(raw.get("end"))
    lo, hi = minutes_of(PHONE_NOTIFY_EARLIEST), minutes_of(PHONE_NOTIFY_LATEST)
    if start is None or end is None:
        return None, "The hours are written HH:MM."
    if start % PHONE_NOTIFY_STEP_MIN or end % PHONE_NOTIFY_STEP_MIN:
        return None, "The hours are on the hour or the half hour."
    if start < lo or end > hi:
        return None, f"The hours stay inside {PHONE_NOTIFY_EARLIEST} to {PHONE_NOTIFY_LATEST} New York time."
    if end <= start:
        return None, "The end comes after the start."
    return {
        "schema_version": PHONE_NOTIFY_SCHEMA_VERSION,
        "hod_momo": raw["hod_momo"],
        **{name: raw[name] for name in _SWITCHES},
        "days": sorted(set(days)),
        "start": raw["start"],
        "end": raw["end"],
    }, None


def check_endpoint(endpoint: Any) -> str | None:
    """Why ``endpoint`` is not a push address the PC will post to; None when it is one."""
    if not isinstance(endpoint, str) or not endpoint or len(endpoint) > PHONE_NOTIFY_ENDPOINT_MAX_CHARS:
        return "That is not a push address."
    parts = urlsplit(endpoint)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or parts.username or parts.password or parts.port not in (None, 443):
        return "A push address is a plain https address."
    if host in PHONE_NOTIFY_PUSH_HOSTS or any(host.endswith(suffix) for suffix in PHONE_NOTIFY_PUSH_HOST_SUFFIXES):
        return None
    return f"{host or 'That host'} is not a push service Nova sends to."


def device_id(endpoint: str) -> str:
    """The short name a phone is listed under: the first 16 hex of the SHA-256 of its push address."""
    return hashlib.sha256(endpoint.encode("utf-8")).hexdigest()[:16]


def _defaults() -> dict[str, Any]:
    return {"schema_version": PHONE_NOTIFY_SCHEMA_VERSION,
            "settings": copy.deepcopy(PHONE_NOTIFY_DEFAULT_SETTINGS), "devices": []}


def _clean_device(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict) or check_endpoint(raw.get("endpoint")) is not None:
        return None
    try:
        if len(webpush.b64url_decode(str(raw.get("p256dh") or ""))) != 65 or len(webpush.b64url_decode(str(raw.get("auth") or ""))) != 16:
            return None
    except (ValueError, TypeError):
        return None
    added = raw.get("added_at")
    return {"id": device_id(raw["endpoint"]), "endpoint": raw["endpoint"], "p256dh": raw["p256dh"],
            "auth": raw["auth"], "added_at": float(added) if isinstance(added, (int, float)) else 0.0}


def load() -> dict[str, Any]:
    """The settings and phones, a copy the caller may change. Read from the file once, then from memory."""
    global _kept
    with _lock:
        file = path()
        if _kept is None or _kept[0] != file:
            _kept = (file, _read(file))
        return copy.deepcopy(_kept[1])


def _read(file: Path) -> dict[str, Any]:
    """The file as kept. Missing: the defaults. Unreadable or of another version: the defaults, said loud."""
    with _lock:
        if not file.is_file():
            return _defaults()
        try:
            doc = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.warning("PHONE NOTIFY: %s is unreadable; notifications are off until it is saved again", file)
            return _defaults()
        if not isinstance(doc, dict) or doc.get("schema_version") != PHONE_NOTIFY_SCHEMA_VERSION:
            logger.warning("PHONE NOTIFY: %s has schema_version %r, not %s; it is not read and notifications "
                           "are off until it is saved again", file, (doc or {}).get("schema_version") if isinstance(doc, dict) else None,
                           PHONE_NOTIFY_SCHEMA_VERSION)
            return _defaults()
        settings, error = normalize_settings(doc.get("settings"))
        if settings is None:
            logger.warning("PHONE NOTIFY: the saved settings are not valid (%s); read as everything off", error)
            settings = copy.deepcopy(PHONE_NOTIFY_DEFAULT_SETTINGS)
        devices = [d for d in (_clean_device(raw) for raw in doc.get("devices") or []) if d is not None]
        return {"schema_version": PHONE_NOTIFY_SCHEMA_VERSION, "settings": settings, "devices": devices}


def _save(doc: dict[str, Any]) -> None:
    global _kept
    from capture.manifest_io import write_json_atomic

    file = path()
    write_json_atomic(file, doc)
    _kept = (file, copy.deepcopy(doc))


def forget_for_tests() -> None:
    """Drop what is kept, so the next read is the file's."""
    global _kept
    with _lock:
        _kept = None


def settings() -> dict[str, Any]:
    return load()["settings"]


def devices() -> list[dict[str, Any]]:
    return load()["devices"]


def save_settings(raw: Any) -> tuple[dict[str, Any] | None, str | None]:
    clean, error = normalize_settings(raw)
    if clean is None:
        return None, error
    with _lock:
        doc = load()
        doc["settings"] = clean
        _save(doc)
    return clean, None


def add_device(endpoint: Any, p256dh: Any, auth: Any, *, now: float | None = None) -> str | None:
    """Subscribe a phone; None when kept, else why not. A phone already listed has its keys replaced."""
    error = check_endpoint(endpoint)
    if error:
        return error
    device = _clean_device({"endpoint": endpoint, "p256dh": p256dh, "auth": auth,
                            "added_at": time.time() if now is None else now})
    if device is None:
        return "The phone's keys are not a push subscription's."
    with _lock:
        doc = load()
        others = [d for d in doc["devices"] if d["id"] != device["id"]]
        if len(others) >= PHONE_NOTIFY_MAX_DEVICES:
            return (f"{PHONE_NOTIFY_MAX_DEVICES} phones are subscribed already. Turn notifications off on one "
                    "you no longer use.")
        doc["devices"] = [*others, device]
        _save(doc)
    return None


def remove_device(endpoint: str) -> bool:
    """Forget a phone by its push address. True when it was listed."""
    gone = device_id(endpoint)
    with _lock:
        doc = load()
        kept = [d for d in doc["devices"] if d["id"] != gone]
        if len(kept) == len(doc["devices"]):
            return False
        doc["devices"] = kept
        _save(doc)
    return True
