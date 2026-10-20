"""The relative-volume table's baselines (#1100): each symbol's last sessions, the epoch rules, and one session's rows.

``build_rvol.py`` reads the files and loops the days; this module holds what carries from one session to the next and
turns one session's minute bars into the table's two row sets. Every rule is ``rvol_store.RULES``; the schema is
``architecture/schema/agent-desk.md`` ("Relative volume across every stock, and what came next").

Memory: a symbol's minute baselines are its last ``BASE_SESSIONS`` cumulative-volume profiles (960 float32 minutes
each), one slot per symbol seen in the last ``BASE_MAX_AGE_DAYS`` days -- about 8,000 slots, 0.6 GB. A slot is freed
when its symbol has not traded for that long (its next session starts a new epoch, so nothing is lost).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd
import pyarrow as pa

from market_reads import rvol_store as rs

N, NDAY, NM = rs.BASE_SESSIONS, rs.DAY_AVG_SESSIONS, rs.MINUTES
NEVER = -(10 ** 8)          # an empty ring entry's day ordinal: older than any age limit

MINUTE_SCHEMA = pa.schema([("date", pa.date32()), ("symbol", pa.string()), ("m", pa.int16()),
                           ("high", pa.float64()), ("low", pa.float64()), ("close", pa.float64()),
                           ("cum", pa.float64()), ("base", pa.float32()),
                           ("vol5", pa.float32()), ("base5", pa.float32())])
DAY_SCHEMA = pa.schema([
    ("date", pa.date32()), ("symbol", pa.string()), ("kind", pa.string()), ("prev_date", pa.date32()),
    ("prev_close", pa.float64()), ("split", pa.string()), ("day_open", pa.float64()), ("day_high", pa.float64()),
    ("day_low", pa.float64()), ("day_close", pa.float64()), ("day_volume", pa.float64()), ("bars", pa.int32()),
    ("first_m", pa.int16()), ("last_m", pa.int16()), ("hi", pa.float64()), ("hi_m", pa.int16()),
    ("lo", pa.float64()), ("lo_m", pa.int16()), ("rth_close", pa.float64()), ("last_close", pa.float64()),
    ("pm_volume", pa.float64()), ("volume", pa.float64()), ("base_sessions", pa.int8()),
    ("day_avg_volume", pa.float64()), ("day_avg_sessions", pa.int8()), ("epoch", pa.int32()),
    ("basis", pa.float64()), ("reset", pa.string())])


@dataclass
class Bars:
    """Minute bars as arrays: ``code`` indexes ``names``; ``m`` is the bar's start in minutes after ET midnight."""
    names: list[str]
    code: np.ndarray
    m: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray

    @classmethod
    def from_frame(cls, frame: pd.DataFrame) -> Bars:
        """From ``symbol, m, high, low, close, volume`` columns (tests, and the table's own rows)."""
        codes, names = pd.factorize(frame["symbol"].to_numpy(dtype=object))
        get = {c: frame[c].to_numpy(dtype=np.float64) if c in frame else np.zeros(len(frame))
               for c in ("high", "low", "close", "volume")}
        return cls(list(names), codes.astype(np.int64), frame["m"].to_numpy(dtype=np.int64), **get)

    @classmethod
    def from_arrow(cls, symbol: pa.ChunkedArray, m: np.ndarray, **columns: np.ndarray) -> Bars:
        encoded = symbol.combine_chunks().dictionary_encode() if len(symbol) else pa.array([], pa.string())
        if len(symbol):
            return cls(encoded.dictionary.to_pylist(), encoded.indices.to_numpy(zero_copy_only=False)
                       .astype(np.int64), m.astype(np.int64), **columns)
        empty = np.zeros(0)
        return cls([], np.zeros(0, np.int64), np.zeros(0, np.int64), empty, empty, empty, empty)


@dataclass
class Session:
    """One session's inputs: its minute bars 04:00-20:00 ET, the day file's rows ``{symbol: (open, high, low, close,
    volume)}``, each symbol's kind and holder (``build_rvol.Reference.kind``) and the movers store's split label."""
    day: str
    bars: Bars
    day_rows: dict[str, tuple]
    kinds: dict[str, str]
    holders: dict[str, str | None] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)


class State:
    """What carries from one session to the next, per symbol."""

    def __init__(self, cap: int = 2048):
        self.slot: dict[str, int] = {}
        self.epoch: dict[str, int] = {}
        self.basis: dict[str, float] = {}
        self.last_seen: dict[str, int] = {}
        self.holder: dict[str, str | None] = {}
        self.last_close: dict[str, tuple[int, str, float]] = {}
        self._alloc(cap)

    def _alloc(self, cap: int) -> None:
        self.cap = cap
        self.prof = np.zeros((cap, N, NM), np.float32)
        self.prof_day = np.full((cap, N), NEVER, np.int32)
        self.prof_basis = np.ones((cap, N))
        self.prof_n = np.zeros(cap, np.int64)
        self.dvol = np.zeros((cap, NDAY))
        self.dvol_day = np.full((cap, NDAY), NEVER, np.int32)
        self.dvol_basis = np.ones((cap, NDAY))
        self.dvol_n = np.zeros(cap, np.int64)
        self.free = list(range(cap - 1, -1, -1))

    def _grow(self) -> None:
        old = self.cap
        grown = {name: getattr(self, name) for name in ("prof", "prof_day", "prof_basis", "prof_n", "dvol",
                                                         "dvol_day", "dvol_basis", "dvol_n")}
        self._alloc(max(old * 3 // 2, old + 1024))
        for name, values in grown.items():
            getattr(self, name)[:old] = values
        self.free = list(range(self.cap - 1, old - 1, -1))

    def slot_of(self, symbol: str) -> int:
        if symbol not in self.slot:
            if not self.free:
                self._grow()
            self.slot[symbol] = self.free.pop()
            self.clear(self.slot[symbol])
        return self.slot[symbol]

    def clear(self, s: int) -> None:
        self.prof_day[s] = NEVER
        self.prof_n[s] = 0
        self.dvol_day[s] = NEVER
        self.dvol_n[s] = 0

    def evict(self, today: int) -> None:
        """Free the slots of symbols not seen for over ``BASE_MAX_AGE_DAYS``: their next session is a new epoch."""
        for symbol in [s for s, seen in self.last_seen.items() if today - seen > rs.BASE_MAX_AGE_DAYS]:
            slot = self.slot.pop(symbol, None)
            if slot is not None:
                self.clear(slot)
                self.free.append(slot)
            for book in (self.epoch, self.basis, self.last_seen, self.holder):
                book.pop(symbol, None)

    def begin(self, symbol: str, today: int, holder: str | None, label: str | None,
              share_factor: float) -> str | None:
        """Start ``symbol``'s session: the epoch reset it causes (``rvol_store.RESETS``) or None, and its basis."""
        reset = None
        if symbol not in self.epoch:
            reset = "first_seen"
        elif holder is not None and holder != self.holder.get(symbol):
            reset = "holder_changed"
        elif label == "likely_split":
            reset = "likely_split"
        slot = self.slot_of(symbol)
        if reset:
            self.clear(slot)
            self.epoch[symbol], self.basis[symbol] = today, 1.0
        else:
            self.basis[symbol] *= share_factor
        self.holder[symbol] = holder
        return reset

    def baselines(self, slots: np.ndarray, basis: np.ndarray, today: int, chunk: int = 512):
        """Per slot: the minute baseline (mean cumulative profile, float64 (len, NM); NaN without a session), its
        session count, the day-volume average and its count -- the baseline sessions' rule, on today's basis."""
        base = np.full((len(slots), NM), np.nan)
        k = np.zeros(len(slots), np.int64)
        for lo in range(0, len(slots), chunk):
            s, b = slots[lo:lo + chunk], basis[lo:lo + chunk]
            valid = self.prof_day[s] >= today - rs.BASE_MAX_AGE_DAYS
            weight = np.where(valid, b[:, None] / self.prof_basis[s], 0.0)
            acc = np.zeros((len(s), NM))
            for j in range(N):
                acc += weight[:, j, None] * self.prof[s, j, :]
            count = valid.sum(axis=1)
            with np.errstate(invalid="ignore", divide="ignore"):
                base[lo:lo + chunk] = np.where(count[:, None] > 0, acc / np.maximum(count, 1)[:, None], np.nan)
            k[lo:lo + chunk] = count
        valid = self.dvol_day[slots] >= today - rs.BASE_MAX_AGE_DAYS
        weight = np.where(valid, basis[:, None] / self.dvol_basis[slots], 0.0)
        count = valid.sum(axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            avg = np.where(count > 0, (weight * self.dvol[slots]).sum(axis=1) / np.maximum(count, 1), np.nan)
        return base, k, avg, count

    def push(self, slots: np.ndarray, profiles: np.ndarray, volumes: np.ndarray, basis: np.ndarray,
             today: int) -> None:
        """Today's cumulative profile and day volume into each slot's ring (the oldest entry drops out)."""
        j = self.prof_n[slots] % N
        self.prof[slots, j] = profiles
        self.prof_day[slots, j] = today
        self.prof_basis[slots, j] = basis
        self.prof_n[slots] += 1
        jd = self.dvol_n[slots] % NDAY
        self.dvol[slots, jd] = volumes
        self.dvol_day[slots, jd] = today
        self.dvol_basis[slots, jd] = basis
        self.dvol_n[slots] += 1


def _to_symbols(bars: Bars, symbols: list[str]):
    """The bars of ``symbols`` only, sorted by symbol then minute, one row per (symbol, minute): ``(row, col, high,
    low, close, volume)`` with ``row`` indexing ``symbols`` and ``col`` the minute's offset from 04:00. Massive
    writes one bar a minute; should a file repeat one, its volume sums, its high is the max, its low the min."""
    index = {s: i for i, s in enumerate(symbols)}
    remap = np.array([index.get(n, -1) for n in bars.names], dtype=np.int64)
    row = remap[bars.code] if len(bars.code) else np.zeros(0, np.int64)
    keep = row >= 0
    row, col = row[keep], bars.m[keep] - rs.SESSION_START_M
    high, low, close, volume = bars.high[keep], bars.low[keep], bars.close[keep], bars.volume[keep]
    order = np.lexsort((col, row))
    row, col, high, low, close, volume = row[order], col[order], high[order], low[order], close[order], volume[order]
    key = row * NM + col
    if len(key) > 1 and (key[1:] == key[:-1]).any():
        first = np.flatnonzero(np.r_[True, key[1:] != key[:-1]])
        last = np.r_[first[1:], len(key)] - 1
        high, low = np.maximum.reduceat(high, first), np.minimum.reduceat(low, first)
        volume, close = np.add.reduceat(volume, first), close[last]
        row, col = row[first], col[first]
    return row, col, high, low, close, volume


def _minute_facts(n: int, row: np.ndarray, col: np.ndarray, high: np.ndarray, low: np.ndarray,
                  close: np.ndarray, volume: np.ndarray) -> dict[str, np.ndarray]:
    """Per symbol (``n`` of them; arrays sorted by row then minute): bars, first / last minute, the session's high
    and low with the first minute that printed each, the regular session's last close, the last close, premarket
    volume and the whole volume (04:00-20:00). Float NaN / minute -1 where a symbol has no bar."""
    m = col + rs.SESSION_START_M
    bars = np.bincount(row, minlength=n)
    out = {"bars": bars, "volume": np.bincount(row, weights=volume, minlength=n),
           "pm_volume": np.bincount(row, weights=np.where(m < rs.RTH_OPEN_M, volume, 0.0), minlength=n)}
    for name in ("first_m", "last_m", "hi_m", "lo_m"):
        out[name] = np.full(n, -1, np.int64)
    for name in ("hi", "lo", "last_close", "rth_close"):
        out[name] = np.full(n, np.nan)
    has = np.flatnonzero(bars)
    if not len(has):
        return out
    start = np.r_[0, np.cumsum(bars[has])[:-1]]
    end = start + bars[has] - 1
    idx = np.arange(len(row))
    out["first_m"][has], out["last_m"][has] = m[start], m[end]
    hi, lo = np.maximum.reduceat(high, start), np.minimum.reduceat(low, start)
    out["hi"][has], out["lo"][has] = hi, lo
    group = np.repeat(np.arange(len(has)), bars[has])
    out["hi_m"][has] = m[np.minimum.reduceat(np.where(high == hi[group], idx, len(row)), start)]
    out["lo_m"][has] = m[np.minimum.reduceat(np.where(low == lo[group], idx, len(row)), start)]
    out["last_close"][has] = close[end]
    rth_last = np.maximum.reduceat(np.where(m < rs.RTH_CLOSE_M, idx, -1), start)
    out["rth_close"][has] = np.where(rth_last >= start, close[np.maximum(rth_last, 0)], np.nan)
    return out


def _f32_or_null(values: np.ndarray) -> pa.Array:
    return pa.array(values.astype(np.float32), mask=np.isnan(values))


def _nullable(values: np.ndarray, missing) -> list:
    return [None if v == missing or (isinstance(v, float) and np.isnan(v)) else v for v in values.tolist()]


def build_session(state: State, session: Session, split_factor) -> tuple[pa.Table, pa.Table, list[int], dict]:
    """One session's ``minutes`` and ``days`` tables (``MINUTE_SCHEMA`` / ``DAY_SCHEMA``), the rows per band, and
    counts. ``split_factor(symbol, prev_day, day, prices)`` is the listed splits' factor in ``(prev_day, day]``."""
    day, today = session.day, rs.ordinal(session.day)
    traded = set(session.bars.names) | set(session.day_rows)
    symbols = sorted(s for s in traded if session.kinds.get(s) in rs.KINDS)
    row, col, high, low, close, volume = _to_symbols(session.bars, symbols)
    state.evict(today)
    resets, prev_dates, prev_closes, splits_out = [], [], [], []
    for symbol in symbols:
        seen = state.last_seen.get(symbol)
        shares = split_factor(symbol, date.fromordinal(seen).isoformat(), day, False) if seen else 1.0
        label = session.labels.get(symbol)
        resets.append(state.begin(symbol, today, session.holders.get(symbol), label, shares))
        last = state.last_close.get(symbol)
        listed = False
        if last and today - last[0] <= rs.PREV_CLOSE_LOOKBACK_DAYS:
            factor = split_factor(symbol, last[1], day, True)
            prev_dates.append(date.fromisoformat(last[1]))
            prev_closes.append(last[2] * factor)
            listed = factor != 1.0
        else:
            prev_dates.append(None)
            prev_closes.append(None)
        splits_out.append("listed" if listed else label if label in ("likely_split", "suspect") else None)
    slots = np.array([state.slot[s] for s in symbols], dtype=np.int64)
    basis = np.array([state.basis[s] for s in symbols])
    base_all, k_all, day_avg, k_day = state.baselines(slots, basis, today)

    cum = np.zeros((len(symbols), NM))
    np.add.at(cum, (row, col), volume)
    np.cumsum(cum, axis=1, out=cum)
    m = (col + rs.SESSION_START_M).astype(np.int16)
    band = np.searchsorted([b[1] for b in rs.BANDS], m, side="right")
    order = np.lexsort((m, row, band))                    # by band, then symbol, then minute
    band_rows = np.bincount(band, minlength=len(rs.BANDS)).tolist()
    r, c = row[order], col[order]
    c5, before5 = np.maximum(c - 5, 0), c >= 5            # (m-5, m] before 04:00 holds nothing
    base_rc = base_all[r, c]
    vol5 = cum[r, c] - np.where(before5, cum[r, c5], 0.0)
    base5 = base_rc - np.where(before5, np.nan_to_num(base_all[r, c5]), 0.0)
    names = np.array(symbols, dtype=object)
    minute_table = pa.table({
        "date": pa.array(np.full(len(order), np.datetime64(day, "D")), pa.date32()),
        "symbol": pa.array(names[r] if len(r) else [], pa.string()), "m": pa.array(m[order]),
        "high": high[order], "low": low[order], "close": close[order], "cum": pa.array(cum[r, c]),
        "base": _f32_or_null(base_rc),
        "vol5": pa.array(vol5.astype(np.float32)), "base5": _f32_or_null(base5)}, schema=MINUTE_SCHEMA)

    facts = _minute_facts(len(symbols), row, col, high, low, close, volume)
    day_file = [session.day_rows.get(s) for s in symbols]

    def from_day(i: int) -> list:
        return [row_[i] if row_ else None for row_ in day_file]

    day_table = pa.table({
        "date": pa.array([date.fromisoformat(day)] * len(symbols), pa.date32()), "symbol": symbols,
        "kind": [session.kinds[s] for s in symbols], "prev_date": pa.array(prev_dates, pa.date32()),
        "prev_close": prev_closes, "split": splits_out, "day_open": from_day(0), "day_high": from_day(1),
        "day_low": from_day(2), "day_close": from_day(3), "day_volume": from_day(4), "bars": facts["bars"],
        **{k: _nullable(facts[k], -1) for k in ("first_m", "last_m", "hi_m", "lo_m")},
        **{k: pa.array(facts[k], mask=np.isnan(facts[k])) for k in ("hi", "lo", "rth_close", "last_close")},
        "pm_volume": facts["pm_volume"], "volume": facts["volume"], "base_sessions": k_all.astype(np.int8),
        "day_avg_volume": pa.array(day_avg, mask=np.isnan(day_avg)), "day_avg_sessions": k_day.astype(np.int8),
        "epoch": [state.epoch[s] for s in symbols], "basis": basis, "reset": resets},
        schema=DAY_SCHEMA)

    state.push(slots, cum.astype(np.float32), facts["volume"], basis, today)
    for i, symbol in enumerate(symbols):
        state.last_seen[symbol] = today
        found = day_file[i]
        if found and found[3] is not None and found[3] > 0:
            state.last_close[symbol] = (today, day, float(found[3]))
    counts = {"stock_days": len(symbols), "bars": int(len(row)),
              "resets": {name: resets.count(name) for name in rs.RESETS if name in resets}}
    return minute_table, day_table, band_rows, counts


def seed(state: State, day: str, bars: Bars, days: pd.DataFrame, holders: dict[str, str | None]) -> None:
    """Replay one already-built session into ``state`` from the table's own rows (its minute ``symbol, m, cum`` --
    ``bars.volume`` holds ``cum`` -- and its days rows) and that day's holders, so a build that starts after it has the baselines a build from the
    start would have."""
    today = rs.ordinal(day)
    state.evict(today)
    symbols = days["symbol"].tolist()
    for symbol, epoch, basis in zip(symbols, days["epoch"].astype(int), days["basis"].astype(float), strict=True):
        slot = state.slot_of(symbol)
        if state.epoch.get(symbol) != epoch:
            state.clear(slot)
        state.epoch[symbol], state.basis[symbol] = epoch, basis
        state.holder[symbol] = holders.get(symbol)
    row, col, _high, _low, _close, cum_at_bars = _to_symbols(bars, symbols)
    cum = np.zeros((len(symbols), NM))
    cum[row, col] = cum_at_bars                 # the stored running total at each bar, carried to the next bar
    np.maximum.accumulate(cum, axis=1, out=cum)
    slots = np.array([state.slot[s] for s in symbols], dtype=np.int64)
    state.push(slots, cum.astype(np.float32), days["volume"].to_numpy(dtype=np.float64),
               days["basis"].to_numpy(dtype=np.float64), today)
    for symbol, close in zip(symbols, days["day_close"].to_numpy(dtype=np.float64), strict=True):
        state.last_seen[symbol] = today
        if close > 0:
            state.last_close[symbol] = (today, day, float(close))
