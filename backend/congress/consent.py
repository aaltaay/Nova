"""The operator's one-time agreement to the reports' use rule, kept on the desk (ADR 066, decision 3).

Owner of ``<cache_dir>/congress/consent.json``: ``{schema_version, accepted_at, text_sha256}``. Nothing is fetched
until it is given. A file of another version, an unreadable one, or one that agreed to other words than
``CONGRESS_CONSENT_TEXT`` reads as "needed": the operator agrees again to the text the page shows.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path

from congress import files
from congress.constants_congress import (
    CONGRESS_CONSENT_CITE,
    CONGRESS_CONSENT_FILE,
    CONGRESS_CONSENT_TEXT,
    CONGRESS_SCHEMA_VERSION,
)

logger = logging.getLogger(__name__)


def path() -> Path:
    return files.folder() / CONGRESS_CONSENT_FILE


def text_sha256() -> str:
    """The fingerprint of the words agreed to: new words ask again."""
    return hashlib.sha256(CONGRESS_CONSENT_TEXT.encode("utf-8")).hexdigest()


def accepted_at() -> float | None:
    """When the agreement to today's text was given; None when it is needed."""
    try:
        doc = json.loads(path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        logger.warning("congress: %s could not be read (%s); the agreement is asked again", CONGRESS_CONSENT_FILE, exc)
        return None
    if not isinstance(doc, dict) or doc.get("schema_version") != CONGRESS_SCHEMA_VERSION:
        return None
    if doc.get("text_sha256") != text_sha256() or not isinstance(doc.get("accepted_at"), (int, float)):
        return None
    return float(doc["accepted_at"])


def given() -> bool:
    return accepted_at() is not None


def accept(now: float | None = None) -> float:
    at = time.time() if now is None else now
    target = path()
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps({"schema_version": CONGRESS_SCHEMA_VERSION, "accepted_at": at,
                               "text_sha256": text_sha256()}), encoding="utf-8")
    os.replace(tmp, target)
    return at


def withdraw() -> None:
    try:
        path().unlink()
    except FileNotFoundError:  # maintainer: allow-swallow nothing kept means it is already withdrawn
        pass


def wire() -> dict:
    at = accepted_at()
    return {"state": "given" if at is not None else "needed", "accepted_at": at,
            "text": CONGRESS_CONSENT_TEXT, "cite": CONGRESS_CONSENT_CITE}
