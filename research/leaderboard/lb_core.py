"""The rebuild's pure core: the as-of grid, time-of-day RVOL, news first-seen and
the per-minute board. No I/O and no clock -- ``lb_io`` reads the flat files into a
``DayInputs``; this turns it into leaderboard rows.

Every row is built by ``leaderboard.rows.make_row`` and every rank comes from
``leaderboard.ranking.rank_rows(rows, BOARD_RULES)``, the function playback, the
S5 universe and live auto-record share.

The no-hindsight rule, in one place: bar ``j`` (window 04:00 + j minutes) closes
at boundary ``k = j + 1`` and is used at every boundary ``k >= j + 1`` -- never at
an earlier one. A boundary ``k`` is ``minute_ts = open_ts + 60 * k`` (04:01..20:00).
"""
from __future__ import annotations

import sys
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from lb_config import BACKEND_DIR, REGULAR_OPEN_J, RVOL_MIN_PRIOR_SESSIONS, SESSION_MINUTES

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from constants_leaderboard import (  # noqa: E402
    LEADERBOARD_BOARD_MARKET,
    LEADERBOARD_RVOL_BASIS_TOD,
    LEADERBOARD_SOURCE_RECONSTRUCTED,
    LEADERBOARD_STATE_REBUILT,
)
from leaderboard.ranking import BOARD_RULES, LEADERS_RULES, S5_RULES, leader_symbols, rank_rows  # noqa: E402
from leaderboard.rows import make_row  # noqa: E402


@dataclass
class DayInputs:
    """One rebuilt session, already filtered to the universe. Bars sorted by (sid, j)."""

    session_date: str
    open_ts: int                    # epoch second of 04:00 ET on session_date
    symbols: list[str]              # sid -> symbol
    sid: np.ndarray                 # int64, per bar
    j: np.ndarray                   # int64, per bar: minutes after 04:00 ET (0..959)
    open: np.ndarray                # float64, per bar
    close: np.ndarray               # float64, per bar
    volume: np.ndarray              # float64, per bar
    prev_close: np.ndarray          # float64 per sid, split-adjusted; nan = unknown
    prior_volume: np.ndarray        # (n_sym, SESSION_MINUTES) split-adjusted volume summed over prior sessions
    prior_sessions: np.ndarray      # int64 per sid: prior sessions in which the symbol printed
    float_shares: list[float | None]
    exchange: list[str | None]
    news_first_ts: np.ndarray       # float64 per sid: earliest article in the news window; nan = none
    news_known: bool                # False -> has_news is unknown (None), never False


def minute_ts_at(open_ts: int, k: int) -> int:
    return int(open_ts) + 60 * int(k)


def cumulative_by_symbol(sid: np.ndarray, volume: np.ndarray) -> np.ndarray:
    """Running volume within each symbol's bars (bars sorted by sid), summed in bar order."""
    out = np.empty(len(volume), dtype=np.float64)
    if len(volume) == 0:
        return out
    starts = np.flatnonzero(np.r_[True, sid[1:] != sid[:-1]])
    ends = np.r_[starts[1:], len(sid)]
    for a, b in zip(starts, ends):
        out[a:b] = np.cumsum(volume[a:b])
    return out


def expand_asof(sid: np.ndarray, j: np.ndarray, n_minutes: int = SESSION_MINUTES) -> tuple[np.ndarray, np.ndarray]:
    """(bar index, boundary k) for every boundary at which that bar is the symbol's latest closed bar.

    Bar ``i`` is the latest closed bar from ``k = j[i] + 1`` through the boundary at
    which the symbol's next bar closes, exclusive -- i.e. through ``j[i + 1]`` -- and
    through ``n_minutes`` for the symbol's last bar. Result sorted by (k, sid).
    """
    n = len(sid)
    if n == 0:
        empty = np.zeros(0, dtype=np.int64)
        return empty, empty
    same_next = np.r_[sid[1:] == sid[:-1], False]
    next_j = np.r_[j[1:], n_minutes]
    end = np.where(same_next, next_j, n_minutes)
    lengths = np.maximum(end - j, 0)   # boundaries j+1 .. end inclusive
    bar = np.repeat(np.arange(n, dtype=np.int64), lengths)
    offsets = np.arange(len(bar), dtype=np.int64) - np.repeat(np.cumsum(lengths) - lengths, lengths)
    k = j[bar] + 1 + offsets
    order = np.lexsort((sid[bar], k))
    return bar[order], k[order]


def tod_rvol(
    prior_volume: np.ndarray,
    prior_sessions: np.ndarray,
    sid: np.ndarray,
    k: np.ndarray,
    cumvol: np.ndarray,
    min_sessions: int = RVOL_MIN_PRIOR_SESSIONS,
) -> np.ndarray:
    """Volume so far over the prior sessions' mean volume by the same boundary; nan = unknown.

    The prior mean at boundary k is the sum over sessions of the bars that had closed
    by the same time of day (j < k), divided by the sessions in which the symbol
    printed. Fewer than ``min_sessions`` such sessions, or a zero mean, is unknown.
    """
    out = np.full(len(k), np.nan)
    if len(k) == 0 or prior_volume.size == 0:
        return out
    csum = np.cumsum(prior_volume, axis=1)
    sessions = prior_sessions[sid].astype(np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        base = csum[sid, k - 1] / sessions
    ok = (prior_sessions[sid] >= min_sessions) & (base > 0)
    out[ok] = cumvol[ok] / base[ok]
    return out


def news_first_seen(
    articles: Iterable[tuple[str, float]],
    window_start_ts: float,
    window_end_ts: float,
) -> dict[str, float]:
    """Earliest publish time per ticker in (window_start_ts, window_end_ts].

    ``articles`` is (ticker, published epoch) -- one article naming a ticker twice
    counts once, and the minimum cannot double-count anyway.
    """
    first: dict[str, float] = {}
    for ticker, ts in articles:
        if ts <= window_start_ts or ts > window_end_ts:
            continue
        sym = str(ticker).strip().upper()
        if sym and (sym not in first or ts < first[sym]):
            first[sym] = float(ts)
    return first


def session_open(sid: np.ndarray, j: np.ndarray, open_: np.ndarray, n_sym: int) -> tuple[np.ndarray, np.ndarray]:
    """Per sid: the j and open price of the first bar at or after 09:30 (j = n_minutes when none)."""
    open_j = np.full(n_sym, SESSION_MINUTES + 1, dtype=np.int64)
    open_px = np.full(n_sym, np.nan)
    rth = np.flatnonzero(j >= REGULAR_OPEN_J)
    if len(rth):
        syms, first = np.unique(sid[rth], return_index=True)
        open_j[syms] = j[rth[first]]
        open_px[syms] = open_[rth[first]]
    return open_j, open_px


def select_rows(rows: Sequence[Mapping[str, Any]], top_n: int) -> list[dict[str, Any]]:
    """The top ``top_n`` by BOARD_RULES plus every LEADERS / S5 pick, carrying BOARD_RULES ranks."""
    ranked = rank_rows(rows, BOARD_RULES)
    keep = {row["symbol"] for row in ranked[: max(0, int(top_n))]}
    keep.update(leader_symbols(rows, LEADERS_RULES))
    keep.update(leader_symbols(rows, S5_RULES))
    return [row for row in ranked if row["symbol"] in keep]


def _none_if_nan(values: np.ndarray) -> list[float | None]:
    return [None if v != v else v for v in values.tolist()]


def day_boards(inp: DayInputs, top_n: int) -> Iterator[tuple[int, list[dict[str, Any]]]]:
    """(minute_ts, stored rows) for every boundary 04:01..20:00 ET, in order."""
    n_sym = len(inp.symbols)
    cumvol = cumulative_by_symbol(inp.sid, inp.volume)
    bar, k = expand_asof(inp.sid, inp.j)
    sid = inp.sid[bar]
    rvol = tod_rvol(inp.prior_volume, inp.prior_sessions, sid, k, cumvol[bar])
    open_j, open_px = session_open(inp.sid, inp.j, inp.open, n_sym)
    with np.errstate(divide="ignore", invalid="ignore"):
        gap = np.where(
            (open_j[sid] <= k - 1) & (inp.prev_close[sid] > 0),
            (open_px[sid] - inp.prev_close[sid]) / inp.prev_close[sid],
            np.nan,
        )
    price, volume = inp.close[bar], cumvol[bar]
    prev = inp.prev_close[sid]
    news = inp.news_first_ts[sid]
    bounds = np.searchsorted(k, np.arange(1, SESSION_MINUTES + 2))
    for step in range(1, SESSION_MINUTES + 1):
        lo, hi = bounds[step - 1], bounds[step]
        minute_ts = minute_ts_at(inp.open_ts, step)
        rows = [
            _row(inp, minute_ts, s, p, pc, v, r, g, nf)
            for s, p, pc, v, r, g, nf in zip(
                sid[lo:hi].tolist(), price[lo:hi].tolist(), _none_if_nan(prev[lo:hi]),
                volume[lo:hi].tolist(), _none_if_nan(rvol[lo:hi]), _none_if_nan(gap[lo:hi]),
                _none_if_nan(news[lo:hi]),
            )
        ]
        yield minute_ts, select_rows(rows, top_n)


def _row(inp: DayInputs, minute_ts: int, s: int, price, prev_close, volume, rvol, gap, news_ts) -> dict[str, Any]:
    if not inp.news_known:
        has_news, first_seen = None, None
    elif news_ts is not None and news_ts <= minute_ts:
        has_news, first_seen = True, news_ts
    else:
        has_news, first_seen = False, None
    return make_row(
        symbol=inp.symbols[s],
        minute_ts=minute_ts,
        board=LEADERBOARD_BOARD_MARKET,
        source=LEADERBOARD_SOURCE_RECONSTRUCTED,
        rank=0,
        price=price,
        prev_close=prev_close,
        volume=volume,
        rvol=rvol,
        rvol_basis=LEADERBOARD_RVOL_BASIS_TOD if rvol is not None else None,
        float_shares=inp.float_shares[s],
        has_news=has_news,
        news_first_seen_ts=first_seen,
        gap_pct=gap,
        exchange=inp.exchange[s],
        market_cap=None,
    )


def coverage_row(session_date: str, minute_ts: int, row_count: int) -> dict[str, Any]:
    return {
        "session_date": session_date,
        "minute_ts": int(minute_ts),
        "source": LEADERBOARD_SOURCE_RECONSTRUCTED,
        "board": LEADERBOARD_BOARD_MARKET,
        "state": LEADERBOARD_STATE_REBUILT,
        "row_count": int(row_count),
        "run_id": None,
    }
