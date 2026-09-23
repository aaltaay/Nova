"""Set the operator's Live arm PIN (ADR 018 amendment, 2026-09-23).

Side effect, on purpose: writes ``NOVA_LIVE_ARM_PIN_HASH`` into the desk's
``.env`` (``NOVA_ENV_PATH`` when set, else the repo root). Only a salted PBKDF2
hash is stored -- the PIN is typed at a hidden prompt, never echoed, logged or
passed on the command line. The running API reads the new hash on its next
Live arm; no restart needed.

    py -3 tools/set_live_arm_pin.py
"""
from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from constants_ibkr import ARM_PIN_HASH_ENV, ARM_PIN_LENGTH  # noqa: E402
from ibkr.arm_pin import hash_pin, valid_pin_shape  # noqa: E402


def env_path() -> Path:
    override = os.environ.get("NOVA_ENV_PATH")
    return Path(override) if override else REPO / ".env"


def write_hash(path: Path, value: str) -> None:
    """Replace the key's line, or append it; every other line is kept as it was."""
    lines = path.read_text(encoding="utf-8-sig").splitlines() if path.is_file() else []
    kept = [line for line in lines if line.split("=", 1)[0].strip() != ARM_PIN_HASH_ENV]
    kept.append(f"{ARM_PIN_HASH_ENV}={value}")
    path.write_text("\n".join(kept) + "\n", encoding="utf-8")


def main() -> int:
    path = env_path()
    first = getpass.getpass(f"New Live PIN ({ARM_PIN_LENGTH} digits): ")
    if not valid_pin_shape(first):
        print(f"The PIN must be exactly {ARM_PIN_LENGTH} digits. Nothing was changed.")
        return 1
    if getpass.getpass("Type it again: ") != first:
        print("The two entries differ. Nothing was changed.")
        return 1
    write_hash(path, hash_pin(first))
    print(f"Live PIN set ({ARM_PIN_HASH_ENV} in {path}). The padlock asks for it on Live.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
