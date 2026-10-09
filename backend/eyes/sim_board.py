"""What the Sim eyes show (ADR 029, ADR 052): the Setups board and the loaded symbol's lanes, built from what the
worker last published (``eyes.sim_eyes``) and the target it follows -- never a lane state from after the playhead.

While a rewind waits for its rebuild the published lanes stand later than the playhead: the board then shows no
rows, cards or proposals and says it is loading, and the symbol view says it is catching up. Pure.
"""
from __future__ import annotations

from typing import Any

from constants_eyes import EYES_REPLAY_SOURCE_SIM
from constants_setups import SETUPS_SCHEMA_VERSION
from eyes.sim_target import KIND_HISTORY, LANE_KINDS

BEHIND_SEC = 1.0          # the published lanes this much past the playhead are ahead of it (a rewind)


def ahead(target: dict, view: dict) -> bool:
    """The published lanes stand later than the playhead (a rewind waiting for its rebuild)."""
    at = view.get("now")
    return target["kind"] in LANE_KINDS and at is not None and float(at) > float(target["playhead"]) + BEHIND_SEC


def note(target: dict, view: dict) -> str | None:
    """What a loaded window's tape gate can read: a Massive window's NBBO is one level, an IBKR download has no
    bid or ask at all."""
    if target["kind"] != KIND_HISTORY:
        return None
    if ((view.get("recording") or {}).get("book")) == "nbbo":
        return "the tape gate reads the window's NBBO (Level 1): a download has no Level 2"
    return "an IBKR download has no bid or ask: the tape reads blind, so nothing goes and the bot enters nothing"


def symbol_view(target: dict | None, view: dict, symbol: str) -> dict[str, Any] | None:
    """The loaded symbol's lanes as published; ``{"pending": why}`` while there is nothing at the playhead to show
    yet; ``None`` when the desk follows no loaded replay of ``symbol``."""
    if target is None or target["kind"] not in LANE_KINDS or str(target.get("symbol") or "").upper() != symbol:
        return None
    if view.get("loading") or view.get("error"):
        return {"pending": view.get("error") or "reading the replay"}
    if ahead(target, view):
        return {"pending": "catching up to the playhead after a rewind"}
    return view.get("symbol") or {"pending": "reading the replay"}


def board(target: dict | None, view: dict, now: float) -> dict[str, Any] | None:
    """The Setups board while the Sim desk shows a replay; ``None`` keeps the live board."""
    from scanner_wire import wire_safe

    if target is None:
        return None
    view = dict(view)
    lanes = target["kind"] in LANE_KINDS
    behind = ahead(target, view)
    if behind:                                  # never a lane state from after the playhead
        view.update(rows=[], proposals=[], setups=[], proposing=False)
    replay_view = {"kind": target["kind"], "date": target.get("date"), "symbol": target.get("symbol"),
                   "playhead": target.get("playhead"), "at": view["now"], "loading": view["loading"] or behind,
                   "error": view["error"], "note": note(target, view) if lanes else view.get("note"),
                   "recording": view["recording"] if lanes else None}
    if target["kind"] == KIND_HISTORY:
        replay_view.update(source=target.get("source"), book=((view["recording"] or {}).get("book")))
    if not lanes:
        replay_view.update(loaded=target.get("loaded"), gap=view.get("gap"), journal=view.get("journal"))
    return wire_safe({
        "schema_version": SETUPS_SCHEMA_VERSION, "generated_at": now, "session_date": target.get("date"),
        "source": EYES_REPLAY_SOURCE_SIM,
        "universe": (1 if target.get("symbol") else 0) if lanes else int(view.get("universe") or 0),
        "universe_symbols": (([target["symbol"]] if target.get("symbol") else []) if lanes
                             else list(view.get("universe_symbols") or [])),
        "seeding": 1 if view["loading"] or behind else 0, "scoreboard": True, "scoreboard_error": None,
        "proposing": lanes and bool(view["proposing"]), "replay": replay_view,
        "setups": view["setups"], "rows": view["rows"], "proposals": view["proposals"],
    })
