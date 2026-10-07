"""Every number a setup runs on (ADR 029): the parameter catalogue.

maintainer: one-concern the one validator for every setup's parameter table (the tables are ``params.py``)

Pure validation: no I/O, no scanner imports. The tables -- one entry per setup the
playbook lists, its parameters grouped, each with a unit, bounds and the default
that is the setup's rule -- are ``params.py``; this module reads them, checks a
template's values against them, fingerprints the scanner's rules and draws them
for the Bots page. ``LEGACY`` keeps a saved template on the rule it ran when a
parameter joins its setup later.

Values are kept in the unit the operator types -- percent as 5, not 0.05; a
float in millions of shares -- and ``setup_scanner/lane_params.py`` converts
them for the scanner in one place. A nullable parameter is off when ``None``.

The ``bot`` group (the bot's entry window, and since ADR 044 the grades it buys and
its setups a stock a day) is the bot's, not the scanner's: it is
left out of ``fingerprint`` -- and so of a template's ``params_hash`` and its rules
revision -- so changing it never starts a read-out over (operator ask 2026-09-30).
``RETIRED`` names parameters that left the catalogue: a stored template that carries
one loads without it; a write that sends one is refused with where it went.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any

from constants_bot import BOT_SETUP_FLAT_TOP, BOT_SETUPS, BOT_SETUPS_WITH_SCANNER
from constants_setups import SETUPS_FT_BASE_LAST_HIGH
from setup_templates.params import (
    BOOL,
    BOT_GROUP,
    CATALOGUE as LONG_CATALOGUE,
    CHOICE,
    DECIMALS,
    GROUP_LABELS as LONG_GROUP_LABELS,
    INT,
    SOURCES as LONG_SOURCES,
    TIME,
    ParamSpec,
    TemplateError,
    minutes,
)
from setup_templates.params_short import SHORT_CATALOGUE, SHORT_GROUP_LABELS, SHORT_SOURCES

# Every setup's table: the long ones (``params.py``), then the short ones (``params_short.py``, ADR 049) --
# in the playbook's order (``constants_bot.BOT_SETUPS``).
CATALOGUE: dict[str, tuple[ParamSpec, ...]] = {
    sid: (LONG_CATALOGUE.get(sid) if sid in LONG_CATALOGUE else SHORT_CATALOGUE[sid])
    for sid in BOT_SETUPS if sid in LONG_CATALOGUE or sid in SHORT_CATALOGUE
}
SOURCES: dict[str, str] = {**LONG_SOURCES, **SHORT_SOURCES}
GROUP_LABELS: dict[str, tuple[str, str]] = {**LONG_GROUP_LABELS, **SHORT_GROUP_LABELS}

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

# Parameters that joined a setup after templates of it were saved, and the value that runs the rule such a template
# ran until then: a stored template that lacks one reads it (``check(..., base=...)``), so adding a parameter never
# changes a saved template's rules. A new template and the built-in default take the catalogue's default.
LEGACY: dict[str, dict[str, Any]] = {
    BOT_SETUP_FLAT_TOP: {"ft_min_touches": 1, "ft_touch_pct": 0.0, "ft_touch_dollars": 0.0,
                         "ft_base_start": SETUPS_FT_BASE_LAST_HIGH},
}

# Parameters that left the catalogue, and where each went. A stored template that carries
# one loads without it (``Template.retired`` keeps what it said, for the Bots page); a
# write that sends one is refused with these words.
RETIRED: dict[str, str] = {
    "bot_entries_per_day": ("Bot entries a day left the template: one daily cap now covers every Nova automatic "
                            "entry on a venue -- the sleeve's entries a day (entries_per_day) on the Bots page."),
}
# The bot's parameters (its entry window): not the scanner's rules, so not in the fingerprint.
BOT_KEYS: frozenset[str] = frozenset(s.key for table in CATALOGUE.values() for s in table if s.group == BOT_GROUP)

# Pairs that must stay in order: (low key, high key, equal allowed, message).
_ORDERED: tuple[tuple[str, str, bool, str], ...] = (
    ("min_price", "max_price", True, "the price floor is over the ceiling"),
    ("min_pullback_bars", "max_pullback_bars", True, "the shortest pullback is longer than the longest"),
    ("min_flag_bars", "max_flag_bars", True, "the shortest flag is longer than the longest"),
    ("session_start", "entry_cutoff", False, "the arming window ends before it starts"),
    ("session_start", "r2g_cutoff", False, "the reclaim window ends before the open"),
    ("bot_window_start", "bot_window_end", False, "the bot's window ends at or before it starts"),
    ("pillar_min_price", "pillar_max_price", True, "the price pillar's floor is over its ceiling"),
    ("wall", "big_seller", True, "the seller that waits is bigger than the one that vetoes"),
    ("macd_fast", "macd_slow", False, "the MACD fast period is not shorter than the slow"),
    ("ft_min_consol", "ft_max_consol", True, "the fewest base candles is more than the most"),
    ("flow_window_sec", "flow_baseline_sec", False, "the flow's pace baseline is not longer than its window"),
)
# Groups of which at least one must be above zero: (keys, message).
_SOME_POSITIVE: tuple[tuple[tuple[str, ...], str], ...] = (
    (("flow_w_imbalance", "flow_w_pace", "flow_w_drift", "flow_w_book"), "every flow weight is zero -- no score"),
)


def setup_ids() -> tuple[str, ...]:
    return tuple(BOT_SETUPS)


def has_scanner(setup_id: str) -> bool:
    return setup_id in BOT_SETUPS_WITH_SCANNER


def specs(setup_id: str) -> tuple[ParamSpec, ...]:
    try:
        return CATALOGUE[setup_id]
    except KeyError:
        raise TemplateError(f"unknown setup {setup_id!r}", code="SETUP_UNKNOWN") from None


def defaults(setup_id: str) -> dict[str, Any]:
    return {s.key: s.default for s in specs(setup_id)}


@dataclass(frozen=True)
class Problem:
    """Why a value map is refused, in the operator's words; ``field`` names the parameter."""

    message: str
    field: str | None = None


def _coerce(spec: ParamSpec, raw: Any) -> Any:
    """The checked value, or the ``Problem`` that refuses it."""
    label = f"{spec.label} ({spec.key})"
    if raw is None:
        return None if spec.nullable else Problem(f"{label} needs a value", spec.key)
    if spec.kind == BOOL:
        return raw if isinstance(raw, bool) else Problem(f"{label} is on or off (true / false)", spec.key)
    if spec.kind == TIME:
        text = str(raw).strip()
        if not _TIME_RE.match(text):
            return Problem(f"{label} is a time like 07:00", spec.key)
        if spec.min is not None and minutes(text) < minutes(str(spec.min)):
            return Problem(f"{label} is {spec.min} ET or later", spec.key)
        if spec.max is not None and minutes(text) > minutes(str(spec.max)):
            return Problem(f"{label} is {spec.max} ET or earlier", spec.key)
        return text
    if spec.kind == CHOICE:
        allowed = [v for v, _ in spec.choices]
        return raw if raw in allowed else Problem(f"{label} is one of {', '.join(allowed)}", spec.key)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return Problem(f"{label} is a number", spec.key)
    value = float(raw)
    if not math.isfinite(value):
        return Problem(f"{label} is a number", spec.key)
    if spec.kind == INT:
        if value != int(value):
            return Problem(f"{label} is a whole number", spec.key)
        value = int(value)
    else:
        value = round(value, DECIMALS)
    if spec.min is not None and value < float(spec.min):
        return Problem(f"{label} is at least {spec.min:g} {spec.unit}".rstrip(), spec.key)
    if spec.max is not None and value > float(spec.max):
        return Problem(f"{label} is at most {spec.max:g} {spec.unit}".rstrip(), spec.key)
    return value


def check(setup_id: str, values: dict[str, Any] | None, *,
          base: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, Problem | None]:
    """``validate`` without raising: ``(checked map, None)``, or ``(None, the first problem)``.

    The store reads a saved template through this, so a template that no longer
    validates keeps its reason as plain words -- no exception is ever caught
    to find it.
    """
    table = {s.key: s for s in specs(setup_id)}
    legacy = {k: v for k, v in LEGACY.get(setup_id, {}).items() if base is not None and k not in base}
    merged = {**defaults(setup_id), **legacy, **{k: v for k, v in (base or {}).items() if k in table}}
    for key in (values or {}):
        if key in RETIRED:
            return None, Problem(RETIRED[key], key)
        if key not in table:
            return None, Problem(f"{key!r} is not a {setup_id.replace('_', ' ')} parameter", key)
    merged.update(values or {})
    out: dict[str, Any] = {}
    for key, spec in table.items():
        value = _coerce(spec, merged.get(key))
        if isinstance(value, Problem):
            return None, value
        out[key] = value
    for low, high, equal_ok, message in _ORDERED:
        if low not in table or high not in table or out[low] is None or out[high] is None:
            continue
        a, b = out[low], out[high]
        if table[low].kind == TIME:
            a, b = minutes(a), minutes(b)
        if a > b or (a == b and not equal_ok):
            return None, Problem(message, high)
    for keys, message in _SOME_POSITIVE:
        if all(k in out for k in keys) and not any((out[k] or 0) > 0 for k in keys):
            return None, Problem(message, keys[0])
    return out, None


def validate(setup_id: str, values: dict[str, Any] | None, *, base: dict[str, Any] | None = None) -> dict[str, Any]:
    """A full, checked value map: ``base`` (else the defaults) with ``values`` over it.

    A key the catalogue does not list is refused, so a typo never saves as a
    silent no-op; a key the base lacks (a parameter added after the template was
    saved) takes its ``LEGACY`` value, else its default -- the rule the template ran
    on until then.
    """
    out, problem = check(setup_id, values, base=base)
    if problem is not None:
        raise TemplateError(problem.message, problem.field)
    return out or {}


def parse_text(setup_id: str, key: str, text: str) -> Any:
    """A value typed on a command line (``flush_exit=tighten``, ``flow_min_r=off``) in the parameter's own kind.

    ``validate`` still checks it; this only reads the words: a nullable parameter reads
    ``none`` / ``null`` / ``off`` as off unless ``off`` is one of its choices."""
    table = {s.key: s for s in specs(setup_id)}
    if key in RETIRED:
        raise TemplateError(RETIRED[key], key)
    if key not in table:
        raise TemplateError(f"{key!r} is not a {setup_id.replace('_', ' ')} parameter", key)
    spec, raw = table[key], text.strip()
    if spec.kind == CHOICE:
        if raw in [v for v, _ in spec.choices]:
            return raw
        return None if spec.nullable and raw.lower() in ("none", "null") else raw
    if spec.nullable and raw.lower() in ("none", "null", "off"):
        return None
    if spec.kind == BOOL:
        words = {"true": True, "on": True, "yes": True, "1": True, "false": False, "off": False, "no": False, "0": False}
        if raw.lower() not in words:
            raise TemplateError(f"{spec.label} ({key}) is on or off", key)
        return words[raw.lower()]
    if spec.kind == TIME:
        return raw
    try:
        return float(raw)
    except ValueError:
        raise TemplateError(f"{spec.label} ({key}) is a number", key) from None


def scanner_values(values: dict[str, Any]) -> dict[str, Any]:
    """The rules the scanner arms, scores and reads the tape with: ``values`` without the bot's
    parameters and without retired ones. A change here is a new rules revision."""
    return {k: v for k, v in values.items() if k not in BOT_KEYS and k not in RETIRED}


def affects_readout(setup_id: str, spec: ParamSpec) -> bool:
    """Whether saving a change to ``spec`` starts the template's read-out over (a new revision)."""
    return has_scanner(setup_id) and spec.group != BOT_GROUP


def fingerprint(values: dict[str, Any]) -> str:
    """A short, stable hash of the scanner's rules in a value map (the audit stamp on a scoreboard
    row, ``params_hash``): the bot's entry window is left out, so it never reads as new rules."""
    blob = json.dumps(scanner_values(values), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def wire(setup_id: str) -> dict[str, Any]:
    """The catalogue for one setup as the Bots page draws it: groups in order."""
    groups: list[dict[str, Any]] = []
    index: dict[str, dict[str, Any]] = {}
    for spec in specs(setup_id):
        if spec.group not in index:
            label, blurb = GROUP_LABELS[spec.group]
            index[spec.group] = {"id": spec.group, "label": label, "blurb": blurb, "params": []}
            groups.append(index[spec.group])
        index[spec.group]["params"].append(spec.wire(affects_readout=affects_readout(setup_id, spec)))
    return {"setup": setup_id, "scanner": has_scanner(setup_id), "source": SOURCES.get(setup_id, ""), "groups": groups}
