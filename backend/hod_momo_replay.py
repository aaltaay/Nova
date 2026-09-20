"""Deterministic HOD Momo replay harness (HOD scanner capture audit).

Replays archived IBKR tape (fixtures from ``tools/export_hod_replay_fixture.py``) through the real
alert engine -- ``hod_momo.on_trade_update`` -- with an injected clock, so results never depend on
the wall clock, market hours, or an IB Gateway login.

Per session: (1) ``reset_engine_state()``, the fresh-engine recipe shared with
``tests/conftest.py``; (2) prime each symbol the way production enrichment/seeding would --
session-high floor from early 1m bars (``apply_session_high``), surge buffer seed from those bars
(``seed_price_buffer``), a ``TickerSnap`` from the fixture meta (prev_close, float; RVOL/gap
stand-ins from the day's production alerts); (3) feed every tape print in ts order with
reconstructed cumulative day volume and a running day-high series (emulates IBKR tick-6), with
``time.time`` / ``market.now_et`` pinned to the replay ts so pace RVOL, session-dependent
min-RVOL, cooldown and consolidation deadlines evaluate on *replay* time; (4) mirror the
consolidation flush (``hod_momo_alerts.flush_consolidated_loop``'s per-strategy grouping) without
disk/WS side effects, collecting emitted alerts for assertions.

Interval-close contract (#385): a bar's ``ts`` is the minute's OPENING stamp, so only minutes
CLOSED by ``first_ts`` seed the high floor and the surge buffer. On the 2026-07-17 fixture the
minute in progress IS the tape step 3 replays -- bar open == first print, high/low == that
minute's print extremes, volume == their sizes to the unit -- so priming from it fed the engine
its own future. Withheld means that bar's final values, never the symbol: with no closed bar a
symbol takes production's live-only seed path and still primes a snapshot price and a 52-week
sentinel from its first observed print.

Fidelity caveats (also in the fixture meta): tape only covers symbols that had an active tape
subscription; avg_volume / live enrichment were not archived, so RVOL stands still at its primed
value unless avg_volume is provided; ``fifty_two_week_high`` is a sentinel. CLI:
``py -3 hod_momo_replay.py --date 2026-07-17`` prints a JSON summary.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterator
from zoneinfo import ZoneInfo

import hod_momo as hm
import hod_momo_high as _high
import hod_momo_market as _market
import hod_momo_metrics as _metrics
import market as _clock_market
from constants import ARCHIVE_BAR_1M_INTERVAL_SEC
from hod_momo_models import alert_to_dict
from hod_momo_state import HodMomoState
from hod_momo_surge_seed import bars_to_surge_points

_ET = ZoneInfo("America/New_York")
_FIFTY_TWO_WEEK_SENTINEL_MULT = 3.0
_DEFAULT_FIXTURE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "tests",
    "fixtures",
    "hod_replay",
)


def reset_engine_state() -> None:
    """Canonical fresh-engine recipe shared with tests/conftest.py."""
    hm.replace_state(HodMomoState())
    hm.load_state()
    state = hm.get_state()
    state.today_alerts = []
    state.pending_consolidation = {}
    state.cooldown = {}
    state.session_highs = {}
    state.session_high_seeded = set()
    state.day_highs = {}
    state.session_high_source = {}
    state.session_high_raised_ts = {}
    state.price_buffer = {}
    state.surge_seeded = set()
    state.pending_surge_seed = set()
    state.ticker_snaps = {}
    state.gate_counters = defaultdict(int)
    state.total_trades_seen = 0
    state.blocklist = set()
    state.startup_ts = time.monotonic() - 10_000
    _metrics.clear_volume_buffers()


@dataclass
class ReplayFixture:
    session_date: str
    tape: list[dict]
    bars_by_symbol: dict[str, list[dict]]
    meta: dict


def load_fixture(session_date: str, fixture_dir: str | None = None) -> ReplayFixture:
    root = fixture_dir or _DEFAULT_FIXTURE_DIR

    def _read_jsonl(name: str) -> list[dict]:
        path = os.path.join(root, name)
        with open(path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    with open(os.path.join(root, f"meta-{session_date}.json"), encoding="utf-8") as f:
        meta = json.load(f)
    tape = _read_jsonl(f"tape-{session_date}.jsonl")
    bars_by_symbol: dict[str, list[dict]] = defaultdict(list)
    for bar in _read_jsonl(f"bars-{session_date}.jsonl"):
        bars_by_symbol[bar["symbol"]].append(bar)
    return ReplayFixture(
        session_date=session_date,
        tape=tape,
        bars_by_symbol=dict(bars_by_symbol),
        meta=meta,
    )


class _ReplayClock:
    def __init__(self, start_ts: float) -> None:
        self.now = float(start_ts)

    def set(self, ts: float) -> None:
        self.now = float(ts)

    def et_now(self) -> datetime:
        return datetime.fromtimestamp(self.now, _ET)


@contextlib.contextmanager
def _pinned_clock(clock: _ReplayClock) -> Iterator[None]:
    """Pin wall clock + ET session clock to replay time (restored on exit)."""
    orig_time = time.time
    orig_now_et = _clock_market.now_et
    time.time = lambda: clock.now  # type: ignore[assignment]
    _clock_market.now_et = clock.et_now  # type: ignore[assignment]
    try:
        yield
    finally:
        time.time = orig_time  # type: ignore[assignment]
        _clock_market.now_et = orig_now_et  # type: ignore[assignment]


@contextlib.contextmanager
def _quiet_trade_log() -> Iterator[None]:
    trade_log = logging.getLogger("hod_momo.trades")
    orig = trade_log.level
    trade_log.setLevel(logging.CRITICAL)
    try:
        yield
    finally:
        trade_log.setLevel(orig)


def _production_enrichment(fixture: ReplayFixture) -> dict[str, dict]:
    """First production alert per symbol -> RVOL/gap/float stand-ins."""
    out: dict[str, dict] = {}
    for alert in fixture.meta.get("production_alerts") or []:
        sym = alert.get("ticker")
        if sym and sym not in out:
            out[sym] = alert
    return out


def closed_bars_before(bars: list[dict], as_of_ts: float) -> list[dict]:
    """Bars whose minute CLOSED by ``as_of_ts`` -- ``ts`` is its OPEN (#385). The fixture-shaped
    twin of ``archive.replay.slice_bars_as_of``."""
    return [b for b in bars or [] if float(b["ts"]) + ARCHIVE_BAR_1M_INTERVAL_SEC <= as_of_ts]


def prime_symbol(
    fixture: ReplayFixture, symbol: str, first_ts: float, *, first_price: float | None = None,
) -> None:
    """Seed one symbol the way production would before live evaluation. ``first_price`` (the
    symbol's first tape print -- the market price at the priming instant) is the last-resort
    stand-in for the snapshot price and the 52-week sentinel; it never feeds the session-high
    floor, so the first print can still register a genuine HOD (#385)."""
    meta = (fixture.meta.get("symbols") or {}).get(symbol) or {}
    prod = _production_enrichment(fixture).get(symbol) or {}
    archived: dict[str, Any] = {}
    try:
        from archive.capture import load_enrichment_snapshot, session_date_for_ts
        archived = load_enrichment_snapshot(symbol, session_date=session_date_for_ts(first_ts)) or {}
    except Exception:
        archived = {}
    bars_before = closed_bars_before(fixture.bars_by_symbol.get(symbol, []), first_ts)

    prev_close = meta.get("prev_close") or None
    seed_candidates = [b["high"] for b in bars_before]
    if prev_close:
        seed_candidates.append(float(prev_close))
    seed_high = max(seed_candidates) if seed_candidates else None
    if seed_high:
        _high.apply_session_high(symbol, float(seed_high), source="bars")
    if bars_before:
        # Production's own function, so low_to_current surge sees each candle's trough (low, then
        # close ~30s later) exactly as it does live.
        _market.seed_price_buffer(symbol, bars_to_surge_points(
            [{"t": b["ts"], "l": b["low"], "c": b["close"]} for b in bars_before]
        ))
    else:
        # No closed bar: production's live-only path (``seed_symbol`` against an empty store) --
        # mark the attempt, and let tick-6 / observed-warmup set the high floor from the tape.
        _market.mark_surge_seed_attempted(symbol)

    float_shares = archived.get("float_shares") or meta.get("float_shares") or prod.get("float_shares")
    avg_volume = archived.get("avg_volume")
    # Stand-ins, never the in-progress bar's final high (#385's lookahead). Without a sentinel any
    # strategy with proximity_52wk_pct > 0 blocks on "52wk_high:unknown" all session.
    snap_base = prev_close or seed_high or first_price
    sentinel_base = seed_high or first_price
    fifty_two = archived.get("fifty_two_week_high")
    if fifty_two is None and sentinel_base:
        fifty_two = float(sentinel_base) * _FIFTY_TWO_WEEK_SENTINEL_MULT
    rvol_source = archived.get("rvol_source") or ("replay_meta" if prod.get("rvol") is not None else None)
    hm.update_ticker_snapshot(
        symbol,
        price=float(snap_base or 0.0),
        change_pct=None,
        rvol=prod.get("rvol"),
        float_shares=float_shares,
        gap_pct=prod.get("gap_pct"),
        fifty_two_week_high=fifty_two,
        rvol_source=rvol_source,
        avg_volume=float(avg_volume) if avg_volume is not None else None,
    )


def _flush_due(state, now_ts: float, sink: list[dict]) -> None:
    """Mirror of flush_consolidated_loop's emit path (no disk/WS/notify)."""
    for symbol in list(state.pending_consolidation.keys()):
        bucket = state.pending_consolidation[symbol]
        ready = [alert for emit_ts, alert in bucket if now_ts >= emit_ts]
        state.pending_consolidation[symbol] = [
            (emit_ts, alert) for emit_ts, alert in bucket if now_ts < emit_ts
        ]
        if not ready:
            continue
        by_strategy: dict[int, list] = {}
        for alert in ready:
            by_strategy.setdefault(int(alert.strategy_id), []).append(alert)
        for group in by_strategy.values():
            primary = group[-1]
            if len(group) > 1:
                primary.consolidation_count = len(group)
                primary.consolidated_ids = [a.id for a in group[:-1]]
                first_ts = min((a.created_ts or 0.0) for a in group) or now_ts
                last_ts = max((a.created_ts or 0.0) for a in group) or now_ts
                span = int(round(max(0.0, last_ts - first_ts)))
                primary.consolidation_span_sec = max(1, span) if span > 0 else 1
            state.today_alerts.insert(0, primary)
            sink.append(alert_to_dict(primary))


@dataclass
class ReplayResult:
    session_date: str
    alerts: list[dict] = field(default_factory=list)
    ticks_per_symbol: dict[str, int] = field(default_factory=dict)
    gate_counters: dict[str, int] = field(default_factory=dict)
    first_ts: float = 0.0
    last_ts: float = 0.0
    pending_unflushed: int = 0

    def alerts_by_symbol_strategy(self) -> dict[str, list[int]]:
        out: dict[str, set[int]] = defaultdict(set)
        for alert in self.alerts:
            out[alert["ticker"]].add(int(alert["strategy_id"]))
        return {sym: sorted(ids) for sym, ids in sorted(out.items())}


def replay_session(
    fixture: ReplayFixture,
    *,
    symbols: list[str] | None = None,
    configure=None,
) -> ReplayResult:
    """Replay one fixture session through the real engine.

    ``configure`` is an optional callable receiving ``state`` after reset so
    callers can restrict/enable strategies or tune the master gate.
    """
    reset_engine_state()
    state = hm.get_state()
    if configure is not None:
        configure(state)

    allowed = {s.upper() for s in symbols} if symbols else None
    tape = [
        row
        for row in fixture.tape
        if allowed is None or row["symbol"].upper() in allowed
    ]
    result = ReplayResult(session_date=fixture.session_date)
    if not tape:
        return result

    first_row_by_symbol: dict[str, dict] = {}
    for row in tape:
        first_row_by_symbol.setdefault(row["symbol"], row)
    first_ts_by_symbol = {sym: float(r["ts"]) for sym, r in first_row_by_symbol.items()}
    for sym, row in first_row_by_symbol.items():
        prime_symbol(fixture, sym, first_ts_by_symbol[sym], first_price=float(row["price"]))

    # Volume base (#385): closed minutes are whole facts; the minute in progress at first_ts is
    # split, so recover only its pre-tape part by subtracting the prints replayed below. Leaks
    # none of that minute's future (unlike the old ``ts <= first_ts`` sum, which also
    # double-counted every print in it) and drops none of its past -- 0.0 on the 2026-07-17
    # fixture, where the bar IS the tape.
    cum_volume: dict[str, float] = {}
    open_minute_end: dict[str, float] = {}
    for sym, first_ts in first_ts_by_symbol.items():
        started = [b for b in fixture.bars_by_symbol.get(sym, []) if float(b["ts"]) <= first_ts]
        cum_volume[sym] = sum(float(b["volume"]) for b in started)
        live = [b for b in started if float(b["ts"]) + ARCHIVE_BAR_1M_INTERVAL_SEC > first_ts]
        if live:
            open_minute_end[sym] = float(live[-1]["ts"]) + ARCHIVE_BAR_1M_INTERVAL_SEC
    for row in tape:
        if float(row["ts"]) < open_minute_end.get(row["symbol"], 0.0):
            cum_volume[row["symbol"]] -= float(row.get("size") or 0.0)
    cum_volume = {sym: max(0.0, base) for sym, base in cum_volume.items()}
    running_high = {
        sym: float(hm.get_state().session_highs.get(sym) or 0.0)
        for sym in first_ts_by_symbol
    }
    prev_close_by_symbol = {
        sym: ((fixture.meta.get("symbols") or {}).get(sym) or {}).get("prev_close")
        for sym in first_ts_by_symbol
    }

    clock = _ReplayClock(tape[0]["ts"])
    result.first_ts = tape[0]["ts"]
    result.last_ts = tape[-1]["ts"]
    ticks: dict[str, int] = defaultdict(int)
    emitted: list[dict] = []

    with _pinned_clock(clock), _quiet_trade_log():
        for row in tape:
            sym = row["symbol"]
            ts = float(row["ts"])
            price = float(row["price"])
            clock.set(ts)
            cum_volume[sym] += float(row.get("size") or 0.0)
            running_high[sym] = max(running_high[sym], price)
            prev_close = prev_close_by_symbol.get(sym)
            if prev_close:
                hm.update_ticker_snapshot(
                    sym,
                    price=price,
                    change_pct=round((price / float(prev_close) - 1.0) * 100.0, 2),
                )
            hm.on_trade_update(
                sym,
                price,
                ts,
                volume=int(cum_volume[sym]),
                day_high=running_high[sym],
            )
            ticks[sym] += 1
            _flush_due(state, ts, emitted)

    result.alerts = emitted
    result.ticks_per_symbol = dict(ticks)
    result.gate_counters = dict(state.gate_counters)
    result.pending_unflushed = sum(
        len(bucket) for bucket in state.pending_consolidation.values()
    )
    return result


def summarize(result: ReplayResult) -> dict:
    return {
        "session_date": result.session_date,
        "ticks": sum(result.ticks_per_symbol.values()),
        "ticks_per_symbol": result.ticks_per_symbol,
        "alerts": len(result.alerts),
        "alerts_by_symbol_strategy": result.alerts_by_symbol_strategy(),
        "pending_unflushed": result.pending_unflushed,
        "gate_counters": result.gate_counters,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", required=True, help="session date YYYY-MM-DD")
    parser.add_argument("--fixture-dir", default=_DEFAULT_FIXTURE_DIR)
    parser.add_argument("--symbols", nargs="*", default=None)
    args = parser.parse_args(argv)

    fixture = load_fixture(args.date, args.fixture_dir)
    result = replay_session(fixture, symbols=args.symbols)
    print(json.dumps(summarize(result), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
