"""Standing nova-brain client (ADR 016). Talks to localhost bot API only."""
from __future__ import annotations

__all__ = ["run_forever"]


def run_forever() -> None:
    from nova_brain.loop import run_forever as _run

    _run()
