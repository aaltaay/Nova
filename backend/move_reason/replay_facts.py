"""One symbol's facts for "Why it's moving" on a Sim replay, as of the playhead (ADR 028 amendment 2026-10-12).

The live read (``facts.gather``) holds today's facts. A replay desk (the Sim off its live edge) reads its own day
instead, every fact from a record that reaches the playhead and nothing after it:

  board row      the recorded (or rebuilt) scanner board at the playhead (``leaderboard.playback.board_at``,
                 ADR 023): price, change, volume, RVOL, the float Nova held then and its #532 check, and the news
                 verdict exported for that day (#498). A rebuilt board carries the float of the session's
                 enrichment snapshot, which may have been taken later that day, so there the float is the newest
                 snapshot taken at or before the playhead instead
  replay         the loaded replay's own last print, previous close (#542) and volume so far, when the replay is
                 this symbol: it wins over the board row for price, change and volume
  news           the board row's verdict, else the recorded catalyst feed's (``catalysts/recorded.py``), with a
                 news halt from the day's halt log
  short interest FINRA's newest settlement published by the replayed day (``move_reason/short_interest.py``)
  borrow         the borrow record at the playhead (``borrow_feed.view_at``)
  split          Massive's split list, splits executed on or before the replayed day (the movers store, ADR 050)
  halts          the day's halt log up to the playhead (``facts.halts_today``)
  shares issued  the recorded feed's 8-Ks of the look-back up to the playhead

A fact no record reaches is ``None``, and ``check_notes`` gives its check the reason, the source it was read from
and its as-of (``rules.read`` applies them). Today's sources -- Yahoo's fundamentals, the live boards, IBKR's
latest borrow poll, the live news memory -- are never read here. Owner: this module (no state).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

from constants_leaderboard import (
    LEADERBOARD_BOARD_GAINERS,
    LEADERBOARD_GAP_FEED_DOWN,
    LEADERBOARD_GAP_NOT_RECORDED,
    LEADERBOARD_GAP_NOT_RUNNING,
    LEADERBOARD_GAP_OUTSIDE_SESSION,
    LEADERBOARD_HALT_SOURCE_NASDAQ,
    LEADERBOARD_SOURCE_RECORDED,
)

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")
# The facts that make a read. Not the halt log: it is read for every day, so on its own a count of none says
# nothing of the stock.
_FACTS = ("change_pct", "volume", "rel_volume", "float_shares", "short_interest", "days_to_cover", "split", "borrow",
          "catalyst")
_GAP_WORDS = {
    LEADERBOARD_GAP_NOT_RUNNING: "Nova's board recorder was not running then",
    LEADERBOARD_GAP_FEED_DOWN: "Nova's board recorded no live feed then",
    LEADERBOARD_GAP_NOT_RECORDED: "Nova recorded no board then",
    LEADERBOARD_GAP_OUTSIDE_SESSION: "it is outside the 04:00-20:00 ET board session",
}
_RVOL_WORDS = {"daily_avg": "volume over the average day", "time_of_day_20": "volume over the 20-day average by this minute"}


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v) if v == v else None


def _day(d: date) -> str:
    return f"{d:%b} {d.day}"


def _clock(ts: float) -> str:
    return datetime.fromtimestamp(ts, ET).strftime("%H:%M ET")


def _try(what: str, fn: Callable[[], Any]) -> Any:
    try:
        return fn()
    except Exception:  # noqa: BLE001 -- a source that fails is unknown; its check says it could not be read
        logger.warning("why it's moving (replay): %s unreadable", what, exc_info=True)
        return None


def readable(facts: dict[str, Any]) -> bool:
    """Whether any record of the stock reached the playhead; with none the answer is ``not_read``."""
    return any(facts.get(k) is not None for k in _FACTS)


def gather(symbol: str, at: float) -> dict[str, Any]:
    sym = (symbol or "").strip().upper()
    day = datetime.fromtimestamp(at, ET).date()
    when = f"{_day(day)} {_clock(at)}"
    notes: dict[str, dict[str, Any]] = {}

    board = _try("the board", lambda: _board_row(sym, at))
    row, row_why = board if board is not None else (None, "Nova's board for the day could not be read")
    quote = _try("the replay", lambda: _replay_quote(sym)) or {}
    price, change, volume, vol_ts, vol_src = None, None, None, None, None
    if quote.get("price") is not None and quote.get("prev_close"):
        price, change = quote["price"], quote["price"] / quote["prev_close"] - 1.0
    elif row is not None:
        price, change = _num(row.get("price")), _num(row.get("change_pct"))
    if quote.get("volume") is not None:
        volume, vol_src, vol_ts = _num(quote["volume"]), f"The replay's volume by {_clock(at)}", at
    elif row is not None and _num(row.get("volume")) is not None:
        volume, vol_ts = _num(row.get("volume")), row["minute_ts"]
        vol_src = f"Volume on Nova's {_board_word(row)} board at {_clock(row['minute_ts'])}"
    float_shares, float_held = _float(row, sym, at)
    rvol = _num(row.get("rvol")) if row is not None else None
    if float_held is not None:
        notes["float"] = {"source": float_held[0] + " (can lag a reverse split or a dilution)", "as_of": float_held[1]}
    if row is not None:
        basis = _RVOL_WORDS.get(str(row.get("rvol_basis") or ""), str(row.get("rvol_basis") or "basis unknown"))
        notes["volume"] = {"source": f"RVOL on Nova's {_board_word(row)} board at {_clock(row['minute_ts'])} ({basis})",
                           "as_of": row["minute_ts"]}
    no_float = row_why or f"No float Nova held for {sym} by {when}"
    if float_shares is None:
        notes["float"] = {"source": f"Yahoo float as Nova held it by {_clock(at)} (its board, else its enrichment "
                                    "snapshot)", "note": no_float}
    if rvol is None:
        notes["volume"] = {"source": f"RVOL on Nova's board by {_clock(at)}",
                           "note": row_why or f"Nova's board row at {when} holds no RVOL"}
    notes["float_rotation"] = {"source": (vol_src or f"Volume by {_clock(at)} (the replay, else Nova's board)")
                               + " over the float", "as_of": vol_ts}
    if volume is None or float_shares is None:
        notes["float_rotation"]["note"] = row_why or (no_float if float_shares is None else f"No volume by {when}")

    from fundamentals import short_above_float

    short, short_note = _short(sym, at, day)
    si = _num((short or {}).get("short_interest"))
    above, above_why = short_above_float(float_shares, si)
    notes["short_interest"] = {"source": (f"FINRA short interest in Massive's archive: the newest settlement published "
                                          f"by {_day(day)}; days to cover is FINRA's, over its average volume"),
                               "note": short_note}
    split, split_why = _try("the split list", lambda: _split(sym, at, day)) or (None, "Massive's split list could not be read")
    notes["reverse_split"] = {"source": f"Massive's split list: the last split executed by {_day(day)}", "note": split_why}
    borrow, borrow_why = _try("the borrow record", lambda: _borrow(sym, at)) or (None, "Nova's borrow record could not be read")
    notes["borrow"] = {"source": f"IBKR's short-stock file as Nova recorded it: the last poll at or before {_clock(at)}",
                       "unknown_value": "Not recorded", "note": borrow_why}
    catalyst, news_note = _news(sym, at, row)
    notes["news"] = {"unknown_value": "No record", "note": news_note}
    from move_reason.facts import halts_today

    halts = halts_today(sym, at)
    notes["halts"] = {"source": f"Nova's halt log for {_day(day)}, up to {_clock(at)}",
                      "note": None if halts is not None else "The halt log could not be read"}
    contradicted = row.get("float_contradicted") if row is not None else None
    from catalysts.recorded import shares_issued_at

    return {
        "symbol": sym,
        "source": "replay",
        "price": price,
        "change_pct": change,
        "volume": volume,
        "rel_volume": rvol,
        "float_shares": float_shares,
        "float_contradicted": contradicted if isinstance(contradicted, bool) else None,
        "float_contradicted_reason": None,
        "short_interest": si,
        "short_interest_ts": (datetime.combine(date.fromisoformat(short["settlement_date"]), datetime.min.time(),
                                               timezone.utc).timestamp() if si is not None else None),
        "short_above_float": above,
        "short_above_float_reason": above_why,
        "short_pct_float": None,
        "days_to_cover": _num((short or {}).get("days_to_cover")),
        "days_to_cover_by": "FINRA",
        "split": split,
        "halts": halts,
        "borrow": borrow,
        "catalyst": catalyst,
        "shares_issued": _try("the share issuances", lambda: shares_issued_at(sym, at)),
        "check_notes": notes,
    }


# -- the sources -------------------------------------------------------------------------------------
def _board_word(row: dict[str, Any]) -> str:
    return "recorded" if row.get("source") == LEADERBOARD_SOURCE_RECORDED else "rebuilt"


def _board_row(sym: str, at: float) -> tuple[dict[str, Any] | None, str | None]:
    """The symbol's row on the board at ``at`` (never after it) and the board's source, or the reason there is none."""
    from leaderboard.playback import board_at

    day = datetime.fromtimestamp(at, ET).date()
    board = board_at(day.isoformat(), at)
    if board.get("gap"):
        reason = _GAP_WORDS.get(board["gap"].get("reason"), "Nova's board has a gap then")
        return None, f"No board row for {sym} at {_day(day)} {_clock(at)}: {reason}"
    boards = board.get("boards") or {}
    for name in [LEADERBOARD_BOARD_GAINERS] + sorted(boards):
        for r in (boards.get(name) or {}).get("rows") or []:
            if r.get("symbol") == sym:
                return {**r, "source": board.get("source"), "minute_ts": board.get("minute_ts")}, None
    return None, f"{sym} was on no Nova board at {_day(day)} {_clock(at)}"


def _float(row: dict[str, Any] | None, sym: str, at: float) -> tuple[float | None, tuple[str, float] | None]:
    """The float and where it was held: the recorded board row's (as the live desk had it that minute), else the
    newest enrichment snapshot taken at or before ``at`` -- a rebuilt row's own is the session's, maybe later."""
    if row is None:
        return None, None
    if row.get("source") == LEADERBOARD_SOURCE_RECORDED:
        held = _num(row.get("float_shares"))
        where = f"Yahoo float as Nova's recorded board held it at {_clock(row['minute_ts'])}"
        return held, ((where, row["minute_ts"]) if held is not None else None)
    snap = _try("the enrichment snapshots", lambda: _snapshot_float(sym, at))
    if snap is None:
        return None, None
    shares, ts = snap
    return shares, (f"Yahoo float in Nova's enrichment snapshot of {_day(datetime.fromtimestamp(ts, ET).date())} "
                    f"{_clock(ts)}", ts)


def _snapshot_float(sym: str, at: float) -> tuple[float, float] | None:
    """``(float, taken at)`` of the newest enrichment snapshot of ``sym`` taken at or before ``at`` (archive.db,
    read-only), or None."""
    import sqlite3

    from constants_archive_news import ARCHIVE_DB_FILENAME
    from paths import cache_root

    path = cache_root() / ARCHIVE_DB_FILENAME
    if not path.is_file():
        return None
    db = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=5.0)
    try:
        row = db.execute("SELECT float_shares, ts FROM enrichment_snapshots WHERE symbol = ? AND ts <= ? "
                         "AND float_shares > 0 ORDER BY ts DESC LIMIT 1", (sym, at)).fetchone()
    finally:
        db.close()
    return (float(row[0]), float(row[1])) if row else None


def _replay_quote(sym: str) -> dict[str, Any] | None:
    """The loaded replay at the playhead when it is this symbol: its last print that sets a price, its previous
    close, and its volume so far when the replay holds the day from 04:00 (else None)."""
    from sim import practice

    active = practice.loaded()
    if active is None or active.symbol != sym:
        return None
    last = practice.reference(sym).last
    if active.source == practice.HISTORICAL:
        from sim import history_playback

        snap = history_playback.snapshot(sym)
        whole_day = snap.get("source") == "trades" and snap.get("stats_scope") == "session"
        return {"price": last, "prev_close": snap.get("prev_close"), "volume": snap.get("volume") if whole_day else None}
    from sim import market_views

    q = market_views.quote(sym) or {}
    return {"price": last, "prev_close": q.get("prev_close"), "volume": q.get("volume")}


def _short(sym: str, at: float, day: date) -> tuple[dict[str, Any] | None, str | None]:
    from move_reason import short_interest

    found = _try("FINRA short interest", lambda: short_interest.published_at(sym, at))
    if found is None:
        return None, "Massive's FINRA short-interest archive could not be read"
    if found.get("reason"):
        return None, found["reason"]
    pending = found.get("pending")
    later = (f"; the {_day(pending['settlement_date'])} settlement counts from {_day(pending['counts_from'])}"
             if pending else "")
    if found.get("row") is None:
        return None, f"No FINRA settlement for {sym} counts by {_day(day)}" + later
    lag = (f"Counted from {_day(found['counts_from'])}: FINRA publishes about seven business days after a "
           f"settlement")
    return found["row"], lag + later


def _split(sym: str, at: float, day: date) -> tuple[dict[str, Any] | None, str | None]:
    from day_movers import store as movers

    db = movers.read_only()
    if db is None:
        return None, "Massive's split list (the movers store) is not on this desk"
    try:
        row = db.execute("SELECT execution_date, split_from, split_to FROM splits WHERE symbol = ? "
                         "AND execution_date <= ? ORDER BY execution_date DESC LIMIT 1", (sym, day.isoformat())).fetchone()
    finally:
        db.close()
    if row is None:
        return {"factor": None, "ts": None, "reverse": None, "days_ago": None}, None
    executed, split_from, split_to = str(row[0]), float(row[1]), float(row[2])
    ts = datetime.combine(date.fromisoformat(executed), datetime.min.time(), ET).timestamp()
    return {"factor": f"{split_to:g}:{split_from:g}", "ts": ts, "reverse": split_to < split_from,
            "days_ago": (at - ts) / 86400}, None


def _borrow(sym: str, at: float) -> tuple[dict[str, Any] | None, str | None]:
    from move_reason import borrow_feed

    if not borrow_feed.enabled():
        return None, "The borrow feed is off on this desk"
    return borrow_feed.get_feed().view_at(sym, at)


def _news(sym: str, at: float, row: dict[str, Any] | None) -> tuple[dict[str, Any] | None, str]:
    """The board row's exported verdict (as the Sim's past-day boards show it), else the recorded feed's."""
    when = f"{_day(datetime.fromtimestamp(at, ET).date())} {_clock(at)}"
    if row is not None and isinstance(row.get("catalyst"), dict):
        return row["catalyst"], f"Items published by {when}, from the day's exported news record"
    from catalysts.live import compact
    from catalysts.recorded import verdict_at
    from catalysts.windows import window_start

    v = _try("the recorded catalyst feed", lambda: verdict_at(sym, at))
    if v is None:
        return None, f"No news source Nova recorded read {sym}'s news from the prior close to {when}"
    v.update(_try("the halt log", lambda: _news_halt(sym, window_start(at), at))
             or {"news_pending": False, "halt_code": None})
    return compact(v), f"Items published by {when}, from Nova's recorded catalyst feed (Alpaca and Finnhub are not recorded)"


def _news_halt(sym: str, start: float, at: float) -> dict[str, Any]:
    """A news halt (T1 / T12) that started in the window and had not resumed by ``at``, from the halt log."""
    from leaderboard import store
    from leaderboard.catalyst_verdicts import halt_view

    days = sorted({datetime.fromtimestamp(t, ET).date().isoformat() for t in (start, at)})
    with store.connect() as db:
        events = [e for d in days for e in store.halt_events(db, d, until=at, symbols=[sym])]
    return halt_view([e for e in events if e.get("source") == LEADERBOARD_HALT_SOURCE_NASDAQ], start, at)
