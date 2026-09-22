"""The one row shape every diagnostics collector produces (ADR 021)."""
from __future__ import annotations

from typing import Any

from constants_diagnostics import (
    DIAG_ACTION_LABELS,
    DIAG_ACTIONS,
    DIAG_STATE_UNKNOWN,
    DIAG_STATES,
)


def row(
    *,
    id: str,  # noqa: A002 -- the payload field is literally ``id``
    group: str,
    title: str,
    state: str,
    detail: str,
    cause: str = "",
    fix: str = "",
    since: float | None = None,
    action: str | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one checklist row. An unknown state or action is refused loudly."""
    if state not in DIAG_STATES:
        raise ValueError(f"diagnostics row {id!r}: unknown state {state!r}")
    if action is not None and action not in DIAG_ACTIONS:
        raise ValueError(f"diagnostics row {id!r}: unknown action {action!r}")
    return {
        "id": id,
        "group": group,
        "title": title,
        "state": state,
        "detail": detail,
        "cause": cause,
        "fix": fix,
        "since": since,
        "action": {"kind": action, "label": DIAG_ACTION_LABELS[action]} if action else None,
        "evidence": dict(evidence or {}),
    }


def unknown_row(
    *,
    id: str,  # noqa: A002
    group: str,
    title: str,
    why: str,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A fact Nova cannot read right now -- always says why."""
    return row(
        id=id,
        group=group,
        title=title,
        state=DIAG_STATE_UNKNOWN,
        detail=f"Unknown: {why}",
        cause=why,
        fix="Open the API log (backend/logs/blast.log) for the underlying error.",
        evidence=evidence,
    )


def counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    out = {state: 0 for state in DIAG_STATES}
    for item in rows:
        out[item["state"]] = out.get(item["state"], 0) + 1
    return out
