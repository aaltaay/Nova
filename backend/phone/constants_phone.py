"""Names and numbers of the phone's door (ADR 070, amendment 2026-11-10)."""
from __future__ import annotations

PHONE_SCHEMA_VERSION = 1

# The one prefix another device may write to (request_guard), and the one mutating /api prefix that is
# opened by its own PIN session instead of X-Nova-Api-Key (auth).
PHONE_API_PREFIX = "/api/phone"

# Where the phone PIN's hash lives in the desk's .env (tools/set_phone_pin.py writes it).
PHONE_PIN_HASH_ENV = "NOVA_PHONE_PIN_HASH"
# The header an unlocked phone sends with every write.
PHONE_SESSION_HEADER = "X-Nova-Phone-Session"
# How long one unlock lasts. A backend restart ends it sooner: the session lives in memory.
PHONE_SESSION_SEC = 8 * 3600.0
# Wrong PINs in a row before the lockout, and how long it lasts (the Live PIN's numbers, counted apart).
PHONE_PIN_MAX_FAILURES = 5
PHONE_PIN_LOCKOUT_SEC = 300.0

# The venues the phone trades (amendment 2026-11-13: Sim too). On Live it looks only.
PHONE_VENUE = "paper"
PHONE_TRADE_VENUES = ("paper", "sim")
# What a phone may ask of the desk's Sim clock: pause / play, and a step to a minute (the desk strip's).
PHONE_SIM_CLOCK_KEYS = frozenset({"paused", "minute_from_open", "symbol"})

PHONE_PIN_REQUIRED = "PHONE_PIN_REQUIRED"
PHONE_PIN_NOT_SET = "PHONE_PIN_NOT_SET"
PHONE_PIN_INVALID = "PHONE_PIN_INVALID"
PHONE_PIN_LOCKED = "PHONE_PIN_LOCKED"
PHONE_LOCKED = "PHONE_LOCKED"
PHONE_LIVE_LOOK_ONLY = "PHONE_LIVE_LOOK_ONLY"
PHONE_NO_VIEW = "PHONE_NO_VIEW"


def is_phone_path(path: str) -> bool:
    normalized = path.rstrip("/") or "/"
    return normalized == PHONE_API_PREFIX or normalized.startswith(PHONE_API_PREFIX + "/")
