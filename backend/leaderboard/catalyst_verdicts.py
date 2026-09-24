"""Each played-back mover's catalyst verdict as known at the Sim playhead (#498; ADR 023, ADR 024).

The research backfill (``research/catalysts/``, whose store the backend never reads) exports into
the leaderboard store, per symbol-day, the sources that looked across the day's window
(``catalyst_checks``) and every item naming the symbol inside it, already labelled by
``catalysts.classify`` (``catalyst_items``; ``research/catalysts/export_leaderboard.py``). A board
read asks this module for the verdict of each symbol on it: ``classify.verdict_from_labels`` over
the items published after the window opened (the prior session's 16:00 ET close) and at or before
the playhead -- never one after it -- in the live desk's wire shape (``catalysts.live.WIRE_KEYS``).

``None`` -- unknown, never "no news" -- when the symbol-day was not exported, or when no source
looked and nothing had been published by then (the live desk's rule). A checked symbol with
nothing published by the playhead is ``none_found``. ``news_pending`` / ``halt_code`` come from the
leaderboard's own halt log: a Nasdaq halt that started inside the window, T1 / T12 with no
resumption logged by the playhead.

Owner: this module (read-only; no state). The store reads are ``leaderboard.store``'s.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

from catalysts.classify import verdict_from_labels
from catalysts.live import compact
from constants_catalysts import CATALYST_NEWS_PENDING_CODES
from constants_leaderboard import (
    LEADERBOARD_HALT_EVENT_END,
    LEADERBOARD_HALT_EVENT_START,
    LEADERBOARD_HALT_SOURCE_NASDAQ,
)
from leaderboard import store
from leaderboard.rows import session_date_for


def sources_of(joined: str | None) -> list[str]:
    """``catalyst_checks.sources_answered`` ('' when no source looked) as a list."""
    return [s for s in (joined or "").split(",") if s]


def _halt_view(events: Iterable[Mapping[str, Any]], start: float, cutoff: float) -> dict[str, Any]:
    """The newest Nasdaq halt that started in (start, cutoff]: its code, and whether it still waits on news."""
    starts = [e for e in events if e.get("event") == LEADERBOARD_HALT_EVENT_START
              and start < float(e.get("ts") or 0) <= cutoff]
    if not starts:
        return {"news_pending": False, "halt_code": None}
    latest = max(starts, key=lambda e: float(e["ts"]))
    code = str(latest.get("code") or "").strip().upper() or None
    resumed = any(e.get("event") == LEADERBOARD_HALT_EVENT_END
                  and float(latest["ts"]) <= float(e.get("ts") or 0) <= cutoff for e in events)
    return {"news_pending": bool(code in CATALYST_NEWS_PENDING_CODES and not resumed), "halt_code": code}


def verdicts_at(
    checks: Iterable[Mapping[str, Any]],
    items: Iterable[Mapping[str, Any]],
    halt_events: Iterable[Mapping[str, Any]],
    *,
    at: float,
    symbols: Iterable[str] | None = None,
) -> dict[str, dict[str, Any] | None]:
    """Symbol -> the wire verdict at ``at`` for every exported symbol-day (limited to ``symbols`` when given).

    Pure. ``items`` and ``halt_events`` may hold more than needed: each is kept to its symbol, to the
    window's opening and to ``at`` (or the window's end, when the sources looked no further).
    """
    wanted = None if symbols is None else {s.upper() for s in symbols}
    by_symbol: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in items:
        by_symbol[str(item.get("symbol") or "").upper()].append(item)
    halts: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for event in halt_events:
        if event.get("source") == LEADERBOARD_HALT_SOURCE_NASDAQ:
            halts[str(event.get("symbol") or "").upper()].append(event)
    out: dict[str, dict[str, Any] | None] = {}
    for check in checks:
        sym = str(check.get("symbol") or "").upper()
        if not sym or (wanted is not None and sym not in wanted):
            continue
        start = float(check["window_start"])
        cutoff = min(float(at), float(check["window_end"]))
        answered = sources_of(check.get("sources_answered"))
        mine = by_symbol.get(sym, [])
        if not answered and not any(start < float(it.get("published_ts") or 0) <= cutoff for it in mine):
            out[sym] = None
            continue
        verdict = verdict_from_labels(mine, window_start=start, cutoff=cutoff, sources_answered=answered,
                                      rules_version=str(check.get("rules_version") or ""))
        verdict.update(_halt_view(halts.get(sym, []), start, cutoff))
        out[sym] = compact(verdict)
    return out


def for_board(
    db: Any,
    day: str,
    at: float,
    checks: list[dict[str, Any]],
    day_events: list[dict[str, Any]],
    symbols: Iterable[str],
) -> dict[str, dict[str, Any] | None]:
    """The verdicts for a board read at ``at``: the day's items up to it, and halts since each window opened.

    ``checks`` are the day's ``store.catalyst_checks``; ``day_events`` the day's halt events up to
    ``at``. A window opens on the prior session, so that session's halt events are read too.
    """
    if not checks:
        return {}
    items = store.catalyst_items(db, day, until=at)
    events = list(day_events)
    for prior in sorted({session_date_for(float(c["window_start"])) for c in checks} - {day}):
        events.extend(store.halt_events(db, prior, until=at))
    return verdicts_at(checks, items, events, at=at, symbols=symbols)
