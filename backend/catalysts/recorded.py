"""A symbol's catalyst verdict and share issuance at a past moment, from the recorded feed (ADR 024; ADR 028
amendment 2026-10-12: "Why it's moving" on a Sim replay).

The live verdict (``catalysts/live.py``) reads what this process holds in memory; a replay's playhead is another
day. Here the same classifier reads the feed's store (``catalyst_feed.sqlite3``, ``catalysts/feed_store.py``):

- the items naming the symbol published after the prior session's 16:00 ET close and at or before ``at`` --
  never one after it -- judged by ``classify.verdict`` at ``at``;
- the sources that read that whole window unbroken: their recorded coverage spans, joined where they overlap
  (each span is unbroken reading, so two that overlap leave no gap), must reach from the window's opening to
  ``at``. Alpaca and Finnhub are read live into memory only, so they never answer here;
- the prior session's own release beside it (v8 ``prior_session``), never counted in it;
- the newest 8-K of the ``CATALYST_ISSUANCE_LOOKBACK_DAYS`` up to ``at`` that says shares were issued.

With no source covering the window and nothing published, the verdict is None (unknown), never "no news".
``news_pending`` is the caller's: it holds the halt log.

Read-only: the store is opened ``mode=ro`` and never created. Owner: this module (no state).
"""
from __future__ import annotations

from typing import Any, Iterable

from catalysts import feed_store
from catalysts.classify import best_placed, shares_issued, verdict
from catalysts.windows import prior_session_open, window_start
from constants_catalysts import CATALYST_FEED_COVERAGE_SOURCES, CATALYST_ISSUANCE_LOOKBACK_DAYS


def covered_sources(spans: Iterable[tuple[str, float, float]], start: float, end: float) -> list[str]:
    """The coverage sources whose spans, joined where they overlap, cover (start, end] without a break. Pure."""
    by_source: dict[str, list[tuple[float, float]]] = {}
    for source, s, e in spans:
        by_source.setdefault(source, []).append((float(s), float(e)))
    out = []
    for source in CATALYST_FEED_COVERAGE_SOURCES:
        reach = start                       # read without a break from ``start`` up to here
        for s, e in sorted(by_source.get(source, ())):
            if s > reach:
                break                       # a gap inside the window
            reach = max(reach, e)
        if reach >= end:
            out.append(source)
    return out


def verdict_at(symbol: str, at: float) -> dict[str, Any] | None:
    """The verdict at ``at`` from the recorded feed, or None when no source covered the window and none spoke
    (or there is no store). Raises ``FeedStoreVersionError`` on a store of another version."""
    sym = (symbol or "").strip().upper()
    db = feed_store.read_only()
    if db is None:
        return None
    try:
        start, opened = window_start(at), prior_session_open(at)
        items = feed_store.items_for(db, sym, opened, at)
        answered = covered_sources(feed_store.spans_since(db, start), start, at)
    finally:
        db.close()
    window = [it for it in items if float(it["published_ts"]) > start]
    if not answered and not window:
        return None
    out = verdict(window, window_start=start, cutoff=at, sources_answered=answered)
    out["prior_session"] = best_placed(items, start=opened, end=start)
    return out


def shares_issued_at(symbol: str, at: float) -> dict[str, Any] | None:
    """The newest 8-K of the look-back up to ``at`` that says shares were issued (``classify.shares_issued``),
    or None -- nothing on file, never "no issuance"."""
    sym = (symbol or "").strip().upper()
    db = feed_store.read_only()
    if db is None:
        return None
    since = at - CATALYST_ISSUANCE_LOOKBACK_DAYS * 86400
    try:
        rows = feed_store.issuance_candidates(db, since)
    finally:
        db.close()
    mine = [it for it in rows if sym in {t.strip().upper() for t in it["tickers"]}]
    return shares_issued(mine, start=since, end=at)
