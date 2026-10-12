"""The target menu's parameters (#845; operator decisions 2026-10-09 and 2026-10-12): one table every setup's
"Risk and targets" group shares, long and short.

A strategy picks a kind for each half -- a fixed amount, the next level of today's map, the pullback's high,
the high of day, or the defaults -- the fixed amount, the first half's share of the shares, and the stop: the
pattern's own, or a few cents under the nearest half / whole dollar. ``setup_scanner/targets.py`` reads them
(``spec_of``); a short reads every kind under its entry (``SHORT``). Pure data.

``LEGACY_KEYS`` are the target parameters a template saved before the menu (``target_mode``, ``target_r``,
``r2g_target_hod``): ``setup_templates/migrate.py`` drops them when it reads a schema-1 file and says what it did
in the template's ``migrated``.
"""
from __future__ import annotations

import dataclasses

from constants_setups import (
    SETUPS_STOP_PATTERN,
    SETUPS_STOP_ROUND,
    SETUPS_STOP_ROUND_CENTS,
    SETUPS_TARGET1_DEFAULT,
    SETUPS_TARGET2_DEFAULT,
    SETUPS_TARGET_FIXED,
    SETUPS_TARGET_FIXED_DOLLARS,
    SETUPS_TARGET_FIXED_MAX,
    SETUPS_TARGET_FIXED_MIN,
    SETUPS_TARGET_HOD,
    SETUPS_TARGET_HOD_OR_LEVEL,
    SETUPS_TARGET_NEXT_LEVEL,
    SETUPS_TARGET_NONE,
    SETUPS_TARGET_PULLBACK_HIGH,
    SETUPS_TARGET_ROUND_OR_FIXED,
    SETUPS_TARGET_SPLIT,
)
from setup_templates.spec import CHOICE, NUMBER, ParamSpec, _p

LEGACY_KEYS = ("target_mode", "target_r", "r2g_target_hod")
_CENTS = f"{round(SETUPS_STOP_ROUND_CENTS * 100):d}c"

TARGETS: tuple[ParamSpec, ...] = (
    _p("target1_kind", "risk", "Target 1", CHOICE, SETUPS_TARGET1_DEFAULT,
       choices=((SETUPS_TARGET_ROUND_OR_FIXED, "the fixed amount, or 1c under a half / whole dollar when that is closer"),
                (SETUPS_TARGET_FIXED, "the fixed amount over the entry"),
                (SETUPS_TARGET_NEXT_LEVEL, "1c under the next level of today's map"),
                (SETUPS_TARGET_PULLBACK_HIGH, "the high the pullback came from"),
                (SETUPS_TARGET_HOD, "1c under the high of day")),
       help="Where the first part sells. A target nearer the entry than 5c is none, and a kind that has none falls "
            "back to the fixed amount."),
    _p("target2_kind", "risk", "Target 2", CHOICE, SETUPS_TARGET2_DEFAULT,
       choices=((SETUPS_TARGET_HOD_OR_LEVEL, "1c under the high of day, else 1c under the next level past target 1"),
                (SETUPS_TARGET_FIXED, "the fixed amount over the entry"),
                (SETUPS_TARGET_NEXT_LEVEL, "1c under the next level of today's map past target 1"),
                (SETUPS_TARGET_PULLBACK_HIGH, "the high the pullback came from"),
                (SETUPS_TARGET_HOD, "1c under the high of day"),
                (SETUPS_TARGET_NONE, "none: everything sells at target 1")),
       help="Where the rest sells, at least 5c past target 1 -- else everything sells at target 1. The stop stays "
            "where it is after target 1."),
    _p("target_fixed", "risk", "Fixed amount", NUMBER, SETUPS_TARGET_FIXED_DOLLARS, unit="$ past the entry",
       min=SETUPS_TARGET_FIXED_MIN, max=SETUPS_TARGET_FIXED_MAX, step=0.01,
       help="The material's 10-30c: a target of a fixed amount, and target 1's fall-back."),
    _p("target_split_pct", "risk", "Sold at target 1", NUMBER, round(SETUPS_TARGET_SPLIT * 100), unit="% of the shares",
       min=10, max=90, step=5, help="With a target 2: this share sells at target 1, the rest at target 2."),
    _p("stop_kind", "risk", "Stop", CHOICE, SETUPS_STOP_PATTERN,
       choices=((SETUPS_STOP_PATTERN, "the pattern's own"),
                (SETUPS_STOP_ROUND, f"{_CENTS} under the nearest half / whole dollar under the entry")),
       help=f"Round: {_CENTS} under the nearest half / whole dollar under the entry, when that risk is inside the "
            "largest risk and over the smallest; otherwise the pattern's stop."),
)

_SHORT_WORDS: dict[str, dict] = {
    "target1_kind": {
        "label": "Cover target 1",
        "choices": ((SETUPS_TARGET_ROUND_OR_FIXED, "the fixed amount, or 1c over a half / whole dollar when that is closer"),
                    (SETUPS_TARGET_FIXED, "the fixed amount under the entry"),
                    (SETUPS_TARGET_NEXT_LEVEL, "1c over the next level of today's map under the entry"),
                    (SETUPS_TARGET_PULLBACK_HIGH, "the low the bounce came from"),
                    (SETUPS_TARGET_HOD, "1c over the low of day")),
        "help": "Where the first part covers. A target nearer the entry than 5c is none, and a kind that has none "
                "falls back to the fixed amount."},
    "target2_kind": {
        "label": "Cover target 2",
        "choices": ((SETUPS_TARGET_HOD_OR_LEVEL, "1c over the low of day, else 1c over the next level past target 1"),
                    (SETUPS_TARGET_FIXED, "the fixed amount under the entry"),
                    (SETUPS_TARGET_NEXT_LEVEL, "1c over the next level of today's map past target 1"),
                    (SETUPS_TARGET_PULLBACK_HIGH, "the low the bounce came from"),
                    (SETUPS_TARGET_HOD, "1c over the low of day"),
                    (SETUPS_TARGET_NONE, "none: everything covers at target 1")),
        "help": "Where the rest covers, at least 5c past target 1 -- else everything covers at target 1. The buy "
                "stop stays where it is after target 1."},
    "target_fixed": {"unit": "$ under the entry"},
    "target_split_pct": {"label": "Covered at target 1",
                         "help": "With a target 2: this share covers at target 1, the rest at target 2."},
    "stop_kind": {"label": "Buy stop",
                  "choices": ((SETUPS_STOP_PATTERN, "the pattern's own"),
                              (SETUPS_STOP_ROUND, f"{_CENTS} over the nearest half / whole dollar over the entry")),
                  "help": f"Round: {_CENTS} over the nearest half / whole dollar over the entry, when that risk is "
                          "inside the largest risk and over the smallest; otherwise the pattern's buy stop."},
}
SHORT: tuple[ParamSpec, ...] = tuple(dataclasses.replace(s, **_SHORT_WORDS.get(s.key, {})) for s in TARGETS)
