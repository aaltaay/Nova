"""An older ``setup-templates.json`` read into this build's schema (persisted-state rule). Pure.

Schema 2 (#845, operator decisions 2026-10-09 and 2026-10-12): the target menu replaced the R-multiple target.
A schema-1 template's ``target_mode`` / ``target_r`` / ``r2g_target_hod`` (``params_targets.LEGACY_KEYS``) are
dropped on read:

- a template that sold at a fixed amount (``target_mode: "fixed"``) keeps it: ``target1_kind: "fixed"``, its
  amount clamped into the menu's 10-30c;
- every other (``r``, ``leg_or_r``, ``leg``, or an R multiple alone) takes the menu's default targets;
- the template's ``rev`` moves on (its scoring changed, so its read-out starts over), and ``migrated`` says in
  words what was done -- the Bots page shows it until the operator saves the template's values.

Nothing is written here: the store writes schema 2 at its next save.
"""
from __future__ import annotations

from typing import Any

from constants_setups import (
    SETUP_TEMPLATES_SCHEMA_VERSION,
    SETUPS_TARGET_FIXED,
    SETUPS_TARGET_FIXED_MAX,
    SETUPS_TARGET_FIXED_MIN,
)
from setup_templates.params_targets import LEGACY_KEYS

FROM_VERSIONS = (1,)


def _template(row: dict[str, Any]) -> dict[str, Any]:
    values = row.get("values") if isinstance(row.get("values"), dict) else {}
    old = {k: values[k] for k in LEGACY_KEYS if k in values}
    if not old:
        return row
    kept = {k: v for k, v in values.items() if k not in LEGACY_KEYS}
    mode = old.get("target_mode")
    if mode == SETUPS_TARGET_FIXED:
        amount = values.get("target_fixed")
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            amount = None
        kept["target1_kind"] = SETUPS_TARGET_FIXED
        text = "It sold target 1 at a fixed amount and still does"
        if amount is not None:
            clamped = min(max(amount, SETUPS_TARGET_FIXED_MIN), SETUPS_TARGET_FIXED_MAX)
            kept["target_fixed"] = round(clamped, 4)
            text += f", {round(clamped * 100):d}c" + ("" if clamped == amount else
                                                       f" (it was ${amount:g}: the menu's fixed amount is 10-30c)")
        text += "; the rest sells at the menu's default target 2."
    else:
        was = (f"target 1 = {mode}" if mode else "target 1") + (
            f" at {float(old['target_r']):g}R" if isinstance(old.get("target_r"), (int, float)) else "")
        text = f"Its {was} became the menu's default targets."
    note = ("2026-10-12 (#845): the R-multiple target left the templates. " + text
            + " Its read-out starts over at this revision.")
    return {**row, "values": kept, "rev": int(row.get("rev") or 1) + 1, "migrated": note}


def to_current(raw: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """``(raw at this build's schema, templates migrated)``; a file already at it comes back as it is."""
    if raw.get("schema_version") not in FROM_VERSIONS:
        return raw, 0
    count = 0
    setups: dict[str, Any] = {}
    for setup_id, entry in (raw.get("setups") or {}).items():
        if not isinstance(entry, dict):
            setups[setup_id] = entry
            continue
        templates = []
        for t in entry.get("templates") or []:
            moved = _template(t) if isinstance(t, dict) else t
            count += moved is not t
            templates.append(moved)
        setups[setup_id] = {**entry, "templates": templates}
    return {**raw, "schema_version": SETUP_TEMPLATES_SCHEMA_VERSION, "setups": setups}, count
