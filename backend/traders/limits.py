"""Each AI trader's limits (ADR 072 decision 7, ``traders.md`` "The limits"): max shares, risk a trade, budget and
flat by. Read here; Settings' column per trader writes them (batch 4).

The file ``trader-limits.json`` in the operator cache: ``{schema_version: 1, traders: {claude: {max_shares, risk_usd,
budget_usd, flat_by}, brain: {...}}, set_at}``. Owner: this module. No file, or a trader or a value missing from it,
reads the defaults (Claude's code values before ADR 072); an unknown version or an unreadable file reads the
defaults, logged and stated in ``error`` -- never a silent guess.
"""
from __future__ import annotations

import json
import logging
import math
import re
from pathlib import Path
from typing import Any

from constants_owners import AI_TRADERS
from constants_traders import (
    TRADER_DEFAULT_BUDGET_USD,
    TRADER_DEFAULT_FLAT_BY,
    TRADER_DEFAULT_MAX_SHARES,
    TRADER_DEFAULT_RISK_USD,
    TRADER_LIMITS_FILE,
    TRADER_LIMITS_SCHEMA_VERSION,
)

logger = logging.getLogger(__name__)

DEFAULTS: dict[str, Any] = {"max_shares": TRADER_DEFAULT_MAX_SHARES, "risk_usd": TRADER_DEFAULT_RISK_USD,
                            "budget_usd": TRADER_DEFAULT_BUDGET_USD, "flat_by": TRADER_DEFAULT_FLAT_BY}
# Each value's rule: whole numbers in their bounds; flat by an ET time from the open to 15:55.
_BOUNDS = {"max_shares": (1, 10_000), "risk_usd": (1, 10_000), "budget_usd": (100, 1_000_000)}
_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def path() -> Path:
    from paths import cache_dir

    return cache_dir() / TRADER_LIMITS_FILE


def problem(key: str, value: Any) -> str | None:
    """The rule a value breaks, in words; None when it keeps it."""
    if key == "flat_by":
        if not isinstance(value, str) or not _HHMM.match(value) or not "09:30" <= value <= TRADER_DEFAULT_FLAT_BY:
            return f"Flat by is an ET time from 09:30 to {TRADER_DEFAULT_FLAT_BY}"
        return None
    low, high = _BOUNDS[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value != int(value):
        return f"{key} is a whole number"
    if not low <= value <= high:
        return f"{key} is between {low:,} and {high:,}"
    return None


def read(at: Path | None = None) -> tuple[dict[str, dict[str, Any]], str | None]:
    """``({trader: limits}, error)``: every AI trader's limits, each value its saved one or its default."""
    target = at or path()
    out = {t: dict(DEFAULTS) for t in AI_TRADERS}
    try:
        doc = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return out, None
    except (OSError, ValueError) as exc:
        logger.warning("TRADERS: %s is unreadable -- the default limits apply", target, exc_info=True)
        return out, f"Nova could not read the saved trader limits ({type(exc).__name__}), so the defaults apply"
    version = doc.get("schema_version") if isinstance(doc, dict) else None
    if version != TRADER_LIMITS_SCHEMA_VERSION:
        logger.warning("TRADERS: %s has schema_version %s; this build reads %s -- the defaults apply",
                       target, version, TRADER_LIMITS_SCHEMA_VERSION)
        return out, (f"The saved trader limits are version {version}; this Nova reads version "
                     f"{TRADER_LIMITS_SCHEMA_VERSION}, so the defaults apply")
    saved = doc.get("traders") if isinstance(doc.get("traders"), dict) else {}
    for trader in AI_TRADERS:
        row = saved.get(trader) if isinstance(saved.get(trader), dict) else {}
        for key in DEFAULTS:
            if key in row and problem(key, row[key]) is None:
                out[trader][key] = row[key] if key == "flat_by" else int(row[key])
    return out, None


def of(trader: str) -> dict[str, Any]:
    """``trader``'s limits now (its defaults for an unknown or unread file)."""
    return read()[0].get(trader, dict(DEFAULTS))


def budget_usd(trader: str) -> int:
    return int(of(trader)["budget_usd"])
