"""The PIN that unlocks the phone: its stored hash, the check, and the lockout.

Owner: this module (``phone.routes`` is the only caller of ``check``).
Which PIN: the desk's own, the one the operator types on the PC (``NOVA_LIVE_ARM_PIN_HASH``), unless a
separate phone PIN is set (``NOVA_PHONE_PIN_HASH``, ``tools/set_phone_pin.py``), which then replaces it
on the phone (operator, 2026-11-12: "Just have the same one as the computer one"). Unlocking the phone
with the desk's PIN arms nothing: it opens the phone's Paper door, and Live is still armed only on the PC.
Stored: in ``.env``, as a salted PBKDF2 hash (``ibkr.arm_pin``), never the PIN. The file is re-read on
every check and wins over the API's environment (which holds the hash it started with), so a PIN set
or changed while the API runs works at once and the old one stops.
Invalidation: the operator sets a new hash. The failure count lives in memory, apart from the count of
wrong PINs typed on the PC, and resets on a correct PIN or a restart.
"""
from __future__ import annotations

import logging
import time

from constants_ibkr import ARM_PIN_HASH_ENV
from ibkr import arm_pin
from phone.constants_phone import (
    PHONE_PIN_HASH_ENV,
    PHONE_PIN_INVALID,
    PHONE_PIN_LOCKED,
    PHONE_PIN_LOCKOUT_SEC,
    PHONE_PIN_MAX_FAILURES,
    PHONE_PIN_NOT_SET,
    PHONE_PIN_REQUIRED,
)

logger = logging.getLogger(__name__)

_failures = 0
_locked_until = 0.0


def stored_hash() -> str | None:
    """The hash the phone's PIN is checked against, as ``.env`` holds it now: the phone's own when one is set,
    else the desk's. The API's environment kept the ones it started with, and a PIN changed on the PC must
    replace the old one at once, not at the next restart."""
    own = arm_pin.read_hash(PHONE_PIN_HASH_ENV, file_first=True)
    if arm_pin.is_hash(own):
        return own
    return arm_pin.read_hash(ARM_PIN_HASH_ENV, file_first=True)


def pin_is_set() -> bool:
    return arm_pin.is_hash(stored_hash())


def check(pin: str | None, *, now: float | None = None) -> tuple[str | None, str]:
    """``(None, "")`` when *pin* is the PIN that unlocks the phone; else ``(code, reason)``."""
    global _failures, _locked_until
    now = time.time() if now is None else now
    if now < _locked_until:
        return PHONE_PIN_LOCKED, f"Too many wrong PINs: the phone is locked for {int(_locked_until - now) + 1} s"
    if not pin:
        return PHONE_PIN_REQUIRED, "The phone needs your PIN to unlock"
    right = arm_pin.matches(stored_hash(), str(pin))
    if right is None:
        return PHONE_PIN_NOT_SET, ("No PIN is set on the desk PC yet: run  py -3 tools/set_live_arm_pin.py  there, "
                                   "then unlock again. The phone uses the same PIN")
    if right:
        _failures = 0
        return None, ""
    _failures += 1
    logger.warning("PHONE: wrong PIN from the phone (%d in a row)", _failures)
    if _failures >= PHONE_PIN_MAX_FAILURES:
        _failures = 0
        _locked_until = now + PHONE_PIN_LOCKOUT_SEC
        return PHONE_PIN_LOCKED, f"Too many wrong PINs: the phone is locked for {int(PHONE_PIN_LOCKOUT_SEC)} s"
    return PHONE_PIN_INVALID, "Wrong PIN"


def reset_for_tests() -> None:
    global _failures, _locked_until
    _failures = 0
    _locked_until = 0.0
