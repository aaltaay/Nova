"""IBKR door vs account vs port -- ADR 013.

Requested door (Paper/Live click), TCP listen port, and managedAccounts kind
are three facts. Switch plans must not treat 4001 LISTEN as a live account.
One Gateway process is one account. One IBC install cannot keep two windows.
Target port already up = reconnect (no 2FA). Target port dark = stop both
listeners, then IBC that door (live can show phone 2FA).
"""
from __future__ import annotations

from typing import Literal

SwitchPlan = Literal["noop", "reconnect", "start_ibc", "replace_target"]


def switch_plan(
    *,
    target: str,
    account_kind: str,
    target_port_listening: bool = False,
    connected_on_target_port: bool = False,
) -> SwitchPlan:
    """What a Paper/Live click should do given account class and target port.

    ``noop`` -- already on that account class; do not restart Gateway.
    ``reconnect`` -- target door port is up; dial it. No kill, no 2FA.
    ``start_ibc`` -- target port is dark; launch stops both listeners then
    starts IBC for this door (one IBC cannot hijack-safe a second window).
    ``replace_target`` -- wrong account class is sitting on the target port.
    """
    door = "live" if str(target).strip().lower() == "live" else "paper"
    kind = str(account_kind or "unknown").strip().lower()
    if kind == door:
        return "noop"
    if (
        target_port_listening
        and connected_on_target_port
        and kind in ("paper", "live")
        and kind != door
    ):
        return "replace_target"
    if target_port_listening:
        return "reconnect"
    return "start_ibc"


def follow_paper_allowed(*, requested_mode: str, intentional: str | None) -> bool:
    """Unattended paper-on-4001 attach. Forbidden during an explicit Live click."""
    requested = "live" if str(requested_mode).strip().lower() == "live" else "paper"
    if requested != "live":
        return False
    if intentional == "live":
        return False
    return True
