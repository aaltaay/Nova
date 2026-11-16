"""Set a separate PIN for the phone (ADR 070, amendment 2026-11-10). Optional since 2026-11-12: with none
set, the phone unlocks with the desk's own PIN. Run this only to give the phone a different one.

Side effect, on purpose: writes ``NOVA_PHONE_PIN_HASH`` into the desk's ``.env`` (``NOVA_ENV_PATH``
when set, else the repo root). Only a salted PBKDF2 hash is stored -- the PIN is typed at a hidden
prompt, never echoed, logged or passed on the command line. The running API reads the new hash on
the phone's next unlock; no restart needed. Run it on the PC: the phone cannot set its own PIN.

    py -3 tools/set_phone_pin.py
"""
from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from constants_ibkr import ARM_PIN_LENGTH  # noqa: E402
from ibkr.arm_pin import hash_pin, valid_pin_shape  # noqa: E402
from phone.constants_phone import PHONE_PIN_HASH_ENV  # noqa: E402


def env_path() -> Path:
    override = os.environ.get("NOVA_ENV_PATH")
    return Path(override) if override else REPO / ".env"


def write_hash(path: Path, value: str) -> None:
    """Replace the key's line, or append it; every other line is kept as it was."""
    lines = path.read_text(encoding="utf-8-sig").splitlines() if path.is_file() else []
    kept = [line for line in lines if line.split("=", 1)[0].strip() != PHONE_PIN_HASH_ENV]
    kept.append(f"{PHONE_PIN_HASH_ENV}={value}")
    path.write_text("\n".join(kept) + "\n", encoding="utf-8")


def main() -> int:
    path = env_path()
    first = getpass.getpass(f"New phone PIN ({ARM_PIN_LENGTH} digits; not your Live PIN): ")
    if not valid_pin_shape(first):
        print(f"The PIN must be exactly {ARM_PIN_LENGTH} digits. Nothing was changed.")
        return 1
    if getpass.getpass("Type it again: ") != first:
        print("The two entries differ. Nothing was changed.")
        return 1
    write_hash(path, hash_pin(first))
    print(f"Phone PIN set ({PHONE_PIN_HASH_ENV} in {path}). The phone asks for it before it sends a Paper order.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
