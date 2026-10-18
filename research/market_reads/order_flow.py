"""Who traded a stock, minute by minute (ADR 059): the per-minute order-flow table built from every trade of the day.

``<NOVA_MARKET_DATA_DIR>/trades_flow_v1/YYYY/MM/YYYY-MM-DD.parquet`` -- one row per (ticker, minute) with at least one
counted print, built by ``research/massive_builders/massive_archive.py process`` (``trades_products.process``); every
column's definition is ``docs/massive-builders.md`` ("trades_flow_v1"). In short: corrections other than 0 / 12 and the
official open / close records are dropped; not-at-market prints (average price, contingent, ...) count only in
``np_vol``; off exchange is Massive exchange 4 (FINRA TRF / ADF: dark pools and wholesalers); a retail buy / sell is
an off-exchange print at $1+ whose hundredths of a cent are 61-99 / 1-39 (the sub-penny rule of Boehmer, Jones,
Zhang and Zhang), 40-60 is a midpoint cross; a sweep is condition 14 on an exchange print; an odd lot is under 100
shares or condition 37; a big print is $25,000+, a block $200,000+.

Derived here, per row: ``off_pct`` (dark-pool / off-exchange share of volume), ``retail_buy_pct`` / ``retail_sell_pct``
(of volume), ``retail_imbalance`` ((buys - sells) / (buys + sells), -1..1), ``sweep_pct``, ``odd_pct``, ``big_pct``,
``block_pct`` -- all percent points of ``vol`` except the imbalance. The sub-penny rule misses retail orders filled
on a whole cent or at the midpoint: retail shares are a lower bound, and the buy / sell split is the signal.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from market_reads import roots

FLOW_DIR = "trades_flow_v1"
KEY = ("ticker", "m")
MAX_COLUMNS = ("max_sz",)
PCT = {"off_pct": "off_vol", "retail_buy_pct": "rb_vol", "retail_sell_pct": "rs_vol", "mid_pct": "mid_vol",
       "sweep_pct": "iso_vol", "odd_pct": "odd_vol", "big_pct": "big_vol", "block_pct": "blk_vol"}
BUCKETS = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "60m": 60, "day": 1440}


def flow_file(day: str) -> Path:
    d = date.fromisoformat(day)
    return roots.massive() / FLOW_DIR / f"{d:%Y}" / f"{d:%m}" / f"{day}.parquet"


def _minute(hhmm: str | None, default: int) -> int:
    if not hhmm:
        return default
    hh, mm = (int(x) for x in hhmm.split(":"))
    return hh * 60 + mm


def _derive(frame: pd.DataFrame) -> pd.DataFrame:
    vol = frame["vol"].where(frame["vol"] > 0)
    for name, column in PCT.items():
        frame[name] = (frame[column] / vol * 100.0).round(2)
    retail = (frame["rb_vol"] + frame["rs_vol"]).where(lambda s: s > 0)
    frame["retail_imbalance"] = ((frame["rb_vol"] - frame["rs_vol"]) / retail).round(3)
    return frame


def order_flow(symbol: str, day: str, start: str | None = None, end: str | None = None,
               bucket: str = "1m") -> pd.DataFrame:
    """``symbol``'s flow on ``day`` between ET ``start`` (inclusive) and ``end`` (exclusive), summed per ``bucket``
    (1m / 5m / 15m / 30m / 60m / day); ``time_et`` is each bucket's first minute. ``attrs['day_total']`` sums the
    window. A minute with no counted print has no row."""
    if bucket not in BUCKETS:
        raise ValueError(f"bucket must be one of {', '.join(BUCKETS)}")
    path = flow_file(day)
    if not path.is_file():
        raise LookupError(f"no {FLOW_DIR} file for {day} at {path} (research/massive_builders/massive_archive.py "
                          "process builds it from the day's trades)")
    import pyarrow.parquet as pq
    symbol = symbol.strip().upper()
    lo, hi = _minute(start, 0), _minute(end, 1440)
    table = pq.read_table(path, filters=[("ticker", "=", symbol), ("m", ">=", lo), ("m", "<", hi)])
    frame = table.to_pandas()
    sums = [c for c in frame.columns if c not in KEY and c not in MAX_COLUMNS]
    if len(frame):
        step = BUCKETS[bucket]
        frame["m"] = frame["m"] // step * step
        agg = {**{c: "sum" for c in sums}, **{c: "max" for c in MAX_COLUMNS if c in frame}}
        frame = frame.groupby("m", sort=True).agg(agg).reset_index()
        frame.insert(0, "time_et", [f"{m // 60:02d}:{m % 60:02d}" for m in frame["m"]])
        frame = _derive(frame)
    total = _derive(frame[sums].sum().to_frame().T) if len(frame) else None
    frame.attrs.update(
        symbol=symbol, day=day, start=start, end=end, bucket=bucket, file=str(path),
        day_total=None if total is None else {k: (None if pd.isna(v) else float(v))
                                              for k, v in total.iloc[0].to_dict().items()},
        units="shares, dollars (dvol), counts (*_n); *_pct percent points of vol; retail_imbalance -1..1; "
              "time_et / m = minute of the ET day",
        rules="docs/massive-builders.md 'trades_flow_v1': off exchange = exchange 4; retail by the sub-penny rule "
              "(a lower bound); sweeps = condition 14 on exchanges; odd < 100 shares or condition 37; big >= $25k; "
              "block >= $200k; not-at-market prints only in np_vol")
    return frame
