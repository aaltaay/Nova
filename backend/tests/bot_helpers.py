"""Shared bot test setup -- Activate + L2 + optional claim/heartbeat."""
from __future__ import annotations

from bot.arming import issue_arm_token, record_heartbeat
from bot.autonomy import apply_desk_level, apply_patch
from bot.persist import load_session, save_session
from bot.session import require_l2_brain


def ready_l2(
    *,
    brain: str | None = "brain-1",
    heartbeat: bool = True,
    symbols: tuple[str, ...] = ("ABCD",),
) -> str:
    token = issue_arm_token()
    apply_patch({"level": 2}, desk=True, arm_token=token)
    row = load_session()
    row["symbol_allowlist"] = list(symbols)
    row["trader_live"] = list(symbols)
    save_session(row)
    if brain:
        require_l2_brain(brain, claim=True)
        if heartbeat:
            record_heartbeat(brain)
    return token


def headers(api_key: str, *, arm: str | None = None, brain: str | None = None) -> dict[str, str]:
    from constants import NOVA_API_KEY_HEADER
    from constants_bot import BOT_DESK_ARM_HEADER

    out = {NOVA_API_KEY_HEADER: api_key}
    if arm:
        out[BOT_DESK_ARM_HEADER] = arm
    if brain:
        out["X-Nova-Brain-Session"] = brain
    return out


__all__ = ["apply_desk_level", "headers", "ready_l2"]
