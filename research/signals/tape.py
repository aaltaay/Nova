"""The tape stage of the signal table: the desk's tape flow score (ADR 034, ``setup_scanner.tape_flow``, the default
template's numbers, as the Signals panel reads it) at every 10 seconds of every in-play minute, from Massive's trades
and NBBO quotes -- each print sided against the last quote strictly before it and the book the NBBO in force (one
level), as the Sim's historical window gives the eyes (``eyes.history_recording``). Per minute: the label and score
at its end, and whether any reading inside it was a flush or a burst.

Not the live tile's input: the live desk sides a print against IBKR's Level 2 when it arrives and reads five levels
of the book; here the side is the SIP's NBBO and the book its top. A day the stage has not reached reads
``not_built``.
"""
from __future__ import annotations

import time
from datetime import date
from types import SimpleNamespace
from typing import Any

import numpy as np
import pyarrow as pa

from market_reads import signals_store as ss

STEP_SEC = 10.0                    # the panel's flow window: one reading per window inside each minute
LEAD_SEC = 180.0                   # prints read before in_play_m, so its first reading has its pace baseline
TAPE_SCHEMA = pa.schema([pa.field("date", pa.date32()), pa.field("symbol", pa.string()), pa.field("m", pa.int16()),
                         pa.field("tape", pa.string()), pa.field("tape_score", pa.float64()),
                         pa.field("tape_flush", pa.bool_()), pa.field("tape_burst", pa.bool_())])


class _Quotes(SimpleNamespace):
    """The NBBO as ``history_recording``'s readers take it: ``ts`` (epoch s) and the bid / ask columns."""

    def __len__(self) -> int:
        return len(self.ts)


def stock_day(day: str, symbol: str, in_play_m: int) -> dict[str, list]:
    """``{m, tape, tape_score, tape_flush, tape_burst}`` for ``m`` from ``in_play_m`` through 15:59."""
    from constants_sim import SIM_MASSIVE_DROPPED_CORRECTIONS, SIM_MASSIVE_EXCHANGES
    from eyes.history_recording import _side, nbbo_books
    from setup_scanner import tape_flow

    from inputs import ts_of
    from market_reads import reads
    start_ts, end_ts = ts_of(day, in_play_m) - LEAD_SEC, ts_of(day, ss.LAST_M + 1)
    window = (_et(start_ts), _et(end_ts))
    trades = reads.trades(symbol, day, *window)
    q = reads.quotes(symbol, day, *window)
    quotes = None
    if len(q):
        bid = q["bid_price"].to_numpy(dtype=np.float64)
        ask = q["ask_price"].to_numpy(dtype=np.float64)
        quotes = _Quotes(ts=(q["sip_timestamp"].to_numpy(dtype=np.int64) / 1e9).tolist(),
                         bid=np.where(bid > 0, bid, np.nan), ask=np.where(ask > 0, ask, np.nan),
                         bid_size=q["bid_size"].to_numpy(dtype=np.float64),
                         ask_size=q["ask_size"].to_numpy(dtype=np.float64))
    prints: list[dict[str, Any]] = []
    if len(trades):
        keep = (~trades["correction"].fillna(0).astype(int).isin(SIM_MASSIVE_DROPPED_CORRECTIONS)
                & ~reads.repeats_a_print(trades["conditions"]))          # an auction counted once, as live
        t = trades[keep]
        for ts_ns, price, size, ex, sets in zip(t["sip_timestamp"], t["price"], t["size"], t["exchange"],
                                                t["sets_price"], strict=True):
            ts = float(ts_ns) / 1e9
            prints.append({"ts": ts, "price": float(price), "size": float(size),
                           "exchange": SIM_MASSIVE_EXCHANGES.get(int(ex), str(ex)),
                           "side": _side(quotes, ts, float(price)) if quotes is not None else None,
                           "sets_price": bool(sets)})
    books = nbbo_books(quotes, [(start_ts, end_ts)]) if quotes is not None else []
    index = tape_flow.FlowIndex(prints, books)
    out: dict[str, list] = {"m": [], "tape": [], "tape_score": [], "tape_flush": [], "tape_burst": []}
    for m in range(int(in_play_m), ss.LAST_M + 1):
        labels, last = [], None
        for k in range(1, int(60 / STEP_SEC) + 1):
            last = index.evaluate(ts_of(day, m) + k * STEP_SEC, tape_flow.DEFAULT_FLOW, history_from=start_ts)
            labels.append(last.get("label"))
        out["m"].append(m)
        out["tape"].append(last.get("label"))
        out["tape_score"].append(last.get("score"))
        out["tape_flush"].append("flush" in labels)
        out["tape_burst"].append("burst" in labels)
    return out


def _et(ts: float) -> str:
    from datetime import datetime

    from inputs import ET
    return datetime.fromtimestamp(ts, ET).strftime("%H:%M")


def build_day(day: str, built: list[str]) -> dict:
    """The tape file of one session already in the signal table (its stock-days, from ``in_play_m``)."""
    import pyarrow.parquet as pq
    t0 = time.monotonic()
    days = pq.read_table(ss.days_path(day)).to_pandas()
    cols: dict[str, list] = {"symbol": [], "m": [], "tape": [], "tape_score": [], "tape_flush": [], "tape_burst": []}
    failed = []
    for symbol, in_play_m in zip(days["symbol"], days["in_play_m"], strict=True):
        try:
            got = stock_day(day, symbol, int(in_play_m))
        except Exception as exc:          # named in the manifest, never silent
            failed.append({"symbol": symbol, "error": f"{type(exc).__name__}: {exc}"[:200]})
            continue
        cols["symbol"] += [symbol] * len(got["m"])
        for c in ("m", "tape", "tape_score", "tape_flush", "tape_burst"):
            cols[c] += got[c]
    n = len(cols["m"])
    arrays = [pa.array([date.fromisoformat(day)] * n, pa.date32())]
    arrays += [pa.array(cols[f.name], f.type, from_pandas=True) for f in list(TAPE_SCHEMA)[1:]]
    ss.write_tape(day, pa.Table.from_arrays(arrays, schema=TAPE_SCHEMA))
    return {"stock_days": len(days) - len(failed), "rows": n, "failed": failed, "built_ts": time.time(),
            "seconds": round(time.monotonic() - t0, 1)}
