"""The built-in template's bot rules (ADR 044): the operator's own values for the default's bot group.

The default is the pre-registered rules and its scanner parameters never change. Its bot group --
when the bot may buy (``bot_window_start`` / ``bot_window_end``), the grades it buys
(``bot_grades``) and its setups a stock a day (``bot_setups_a_day``) -- is the operator's to set
from the Bots page, because those never change a template's rules, its revision or its read-out.
They are kept per setup as ``setups.{SETUP}.default_bot: {KEY: value}`` in ``setup-templates.json``
(schema 1: a file without it reads as no overrides), only the values that differ from the
catalogue's defaults, and laid over the defaults wherever the default's values are read.

Pure: the store (``setup_templates.store``) reads and writes the file. A stored value that no longer
validates is dropped with a warning in the log -- the pre-registered value applies -- and the next
save of that setup's bot rules writes the file without it.
"""
from __future__ import annotations

import logging
from typing import Any

from setup_templates import catalogue
from setup_templates.catalogue import TemplateError

logger = logging.getLogger(__name__)
LOCKED = ("the default is the pre-registered rules and stays as it is -- duplicate it to make a variation. "
          "Only its bot rules (the bot's window, the grades it buys, its setups a stock a day) can be set")


def bot_keys(setup_id: str) -> list[str]:
    """The bot group's parameters of ``setup_id``, in the catalogue's order."""
    return [s.key for s in catalogue.specs(setup_id) if s.group == catalogue.BOT_GROUP]


def clean(setup_id: str, raw: Any) -> dict[str, Any]:
    """The stored overrides that still validate, over the defaults; each one that does not is dropped (logged)."""
    if not isinstance(raw, dict):
        return {}
    keys = set(bot_keys(setup_id))
    kept = {k: v for k, v in raw.items() if k in keys}
    for k in raw:
        if k not in keys:
            logger.warning("setup templates: %s default_bot %r is not a bot parameter -- ignored", setup_id, k)
    while kept:
        _checked, problem = catalogue.check(setup_id, kept, base=catalogue.defaults(setup_id))
        if problem is None:
            break
        bad = problem.field if problem.field in kept else next(iter(kept))
        logger.warning("setup templates: %s default_bot %s=%r no longer validates (%s) -- the pre-registered "
                       "value applies", setup_id, bad, kept[bad], problem.message)
        kept.pop(bad)
    defaults = catalogue.defaults(setup_id)
    return {k: v for k, v in kept.items() if v != defaults.get(k)}


def values(setup_id: str, overrides: dict[str, Any] | None) -> dict[str, Any]:
    """The default's values with the operator's bot rules over them."""
    return {**catalogue.defaults(setup_id), **(overrides or {})}


def changes(setup_id: str, current: dict[str, Any], patch: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """``(merged values, overrides to store)`` for a PATCH of the default; a change to anything but the bot
    group is refused ``TEMPLATE_BUILTIN`` (a value sent equal to the default's own is not a change)."""
    merged = catalogue.validate(setup_id, patch, base=current)
    keys = set(bot_keys(setup_id))
    moved = [k for k in (patch or {}) if k not in keys and merged.get(k) != current.get(k)]
    if moved:
        raise TemplateError(LOCKED, moved[0], code="TEMPLATE_BUILTIN")
    defaults = catalogue.defaults(setup_id)
    return merged, {k: merged[k] for k in bot_keys(setup_id) if merged.get(k) != defaults.get(k)}
