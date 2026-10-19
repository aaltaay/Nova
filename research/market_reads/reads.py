"""One stock-day out of the Massive files as a table, and the day movers index and past-day boards without the API.

Every row of a file comes back as delivered (Massive's columns, its nanosecond SIP times) plus ``time_et``; nothing is
adjusted for splits, and nothing is filtered but the window asked for -- except the bars built from trades, which
follow the Sim's own print rules (``sim.massive_files.trade`` / ``sets_price``). The reads go through
``sim.massive_files.DayRead``: about a second on a day whose index is built, minutes on one whose index is not.
"""
from __future__ import annotations

import io
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from market_reads import REPO  # noqa: F401  (puts backend/ on sys.path)

from constants_sim import (
    SIM_MASSIVE_DROPPED_CORRECTIONS,
    SIM_MASSIVE_MINUTES,
    SIM_MASSIVE_QUOTES,
    SIM_MASSIVE_TRADES,
)
from sim import massive_files

ET = ZoneInfo("America/New_York")
TF_UNITS = {"s": 1, "m": 60, "h": 3600}
BOARD_PCT_COLUMNS = ("change_pct", "gap_pct")   # the board store keeps fractions; answered in percent points
TEXT_COLUMNS = {"ticker": str, "conditions": str, "indicators": str, "id": str}
# Only an empty field is missing: pandas' default NA strings ("NA", "NULL", "N/A", ...) are real tickers.
CSV_NA = {"keep_default_na": False, "na_values": [""]}
TIME_COLUMN = {SIM_MASSIVE_TRADES: "sip_timestamp", SIM_MASSIVE_QUOTES: "sip_timestamp",
               SIM_MASSIVE_MINUTES: "window_start"}# The board each list reads on a recorded day and on a rebuilt one (a rebuilt day's Gainers is its market board).
LIST_BOARD = {
    "recorded": {"gainers": "gainers", "losers": "losers", "gappers": "gappers", "afterhours": "afterhours",
                 "large_cap": "large_cap"},
    "reconstructed": {"gainers": "market", "losers": "losers", "gappers": "gappers", "afterhours": "afterhours"},
}


def _ns(day: str, hhmm: str) -> int:
    hh, mm = (int(part) for part in hhmm.split(":"))
    d = date.fromisoformat(day)
    return int(datetime(d.year, d.month, d.day, hh, mm, tzinfo=ET).timestamp()) * 10**9


def _in_window(lines: list[bytes], header: list[str], column: str, lo: int | None, hi: int | None) -> list[bytes]:
    """The lines whose ``column`` may lie in ``[lo, hi)``, so the rest never reach the full CSV parse. pyarrow reads
    only that column (a real CSV parser: quoted commas in the conditions are fields, not separators). A line whose
    time is empty is kept, and a stretch pyarrow cannot read as whole numbers keeps every line: the parsed frame then
    decides, as it does for every row. Nothing about row order is assumed."""
    import pyarrow as pa
    import pyarrow.csv as pacsv
    try:
        table = pacsv.read_csv(io.BytesIO(b"\n".join(lines) + b"\n"),
                               read_options=pacsv.ReadOptions(column_names=header),
                               convert_options=pacsv.ConvertOptions(include_columns=[column],
                                                                    column_types={column: pa.int64()}))
    except pa.ArrowInvalid:
        return lines
    if table.num_rows != len(lines):
        return lines
    times = table.column(0)
    known = times.is_valid().to_numpy(zero_copy_only=False)
    times = times.fill_null(0).to_numpy()
    inside = np.ones(len(lines), dtype=bool)
    if lo is not None:
        inside &= times >= lo
    if hi is not None:
        inside &= times < hi
    return [lines[i] for i in np.flatnonzero(~known | inside)]


def read_file(dataset: str, symbol: str, day: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """``symbol``'s rows of ``dataset`` on ``day`` (ET ``start`` <= time < ``end``), every column as delivered.

    A window is applied to the raw lines before the CSV parse (``_in_window``), so a few minutes of a busy day parse
    only those minutes. ``df.attrs`` says whether the read went through the file's index (``indexed``), how long it
    took, and how many of the block's lines were read and parsed (``lines_read``, ``lines_parsed``).
    """
    path = massive_files.day_file(dataset, day)
    if path is None:
        raise LookupError(f"no {dataset} file for {day} under {massive_files.root()}")
    t0 = datetime.now()
    column = TIME_COLUMN[dataset]
    lo = _ns(day, start) if start else None
    hi = _ns(day, end) if end else None
    header: list[str] | None = None
    lines: list[bytes] = []
    read_count = 0
    with massive_files.DayRead(path, symbol) as read:
        for head, batch in read.batches():
            header = head or header
            read_count += len(batch)
            lines.extend(_in_window(batch, header, column, lo, hi) if (start or end) and column in header else batch)
        indexed = read.indexed
    if not lines:
        frame = pd.DataFrame(columns=header or [])
    else:
        text = (",".join(header or []) + "\n").encode() + b"\n".join(lines) + b"\n"
        frame = pd.read_csv(io.BytesIO(text), dtype={k: v for k, v in TEXT_COLUMNS.items() if k in (header or [])},
                            **CSV_NA)
    if len(frame):
        if start:
            frame = frame[frame[column] >= _ns(day, start)]
        if end:
            frame = frame[frame[column] < _ns(day, end)]
        frame = frame.reset_index(drop=True)
        frame.insert(0, "time_et", pd.to_datetime(frame[column], unit="ns", utc=True).dt.tz_convert(ET))
    frame.attrs.update(dataset=dataset, symbol=symbol.upper(), day=day, indexed=indexed,
                       seconds=round((datetime.now() - t0).total_seconds(), 2), file=str(path),
                       lines_read=read_count, lines_parsed=len(lines))
    return frame


def trades(symbol: str, day: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """Every trade, plus ``sets_price``: the print may move the last or a candle (the SIP's rules, ADR 046)."""
    frame = read_file(SIM_MASSIVE_TRADES, symbol, day, start, end)
    if len(frame):
        frame["sets_price"] = [massive_files.sets_price(c if isinstance(c, str) else "", int(k))
                               for c, k in zip(frame["conditions"], frame["correction"].fillna(0), strict=True)]
    return frame


def quotes(symbol: str, day: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """Every NBBO change: one best bid and one best offer across venues (Level 1, never depth). A side Massive
    writes as 0 has no quote."""
    return read_file(SIM_MASSIVE_QUOTES, symbol, day, start, end)


def _seconds(tf: str) -> int:
    tf = str(tf).strip().lower()
    if tf.endswith("d") or tf.endswith("w"):
        raise ValueError(f"tf {tf!r} is not a stock-day read: daily bars come from day_aggs_v1 through the "
                         "daily_bars tool (market_data.py daily); stock_day bars are 1s..60m inside one day")
    unit, count = tf[-1:], tf[:-1]
    if unit not in TF_UNITS or not count.isdigit() or int(count) < 1:
        raise ValueError(f"tf must be a number and s, m or h (10s, 1m, 5m, 1h), not {tf!r}")
    return int(count) * TF_UNITS[unit]


def bars(symbol: str, day: str, tf: str = "1m", start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """OHLCV bars. Minutes (``1m``, ``5m``, ...) from the minute file, as delivered and summed; seconds (``10s``)
    from the trades by the Sim's rules: a cancel or error record is no trade, only a price-setting print sets
    open / high / low / close, and every trade counts in the volume. A bar with no price-setting print has no
    prices (its volume stands)."""
    step = _seconds(tf)
    if step % 60 == 0:
        frame = read_file(SIM_MASSIVE_MINUTES, symbol, day, start, end)
        if not len(frame):
            return frame
        frame["bucket"] = frame["window_start"] // (step * 10**9) * step
        out = frame.groupby("bucket", sort=True).agg(open=("open", "first"), high=("high", "max"),
                                                      low=("low", "min"), close=("close", "last"),
                                                      volume=("volume", "sum"), transactions=("transactions", "sum"))
    else:
        prints = trades(symbol, day, start, end)
        if not len(prints):
            return prints
        kept = prints[~prints["correction"].fillna(0).astype(int).isin(SIM_MASSIVE_DROPPED_CORRECTIONS)].copy()
        kept["bucket"] = kept["sip_timestamp"] // (step * 10**9) * step
        priced = kept[kept["sets_price"]]
        volume = kept.groupby("bucket")["size"].agg(["sum", "count"]).rename(columns={"sum": "volume",
                                                                                    "count": "transactions"})
        ohlc = priced.groupby("bucket")["price"].agg(open="first", high="max", low="min", close="last")
        out = volume.join(ohlc, how="left")[["open", "high", "low", "close", "volume", "transactions"]]
    out = out.reset_index()
    out.insert(0, "time_et", pd.to_datetime(out.pop("bucket"), unit="s", utc=True).dt.tz_convert(ET))
    out.attrs.update(symbol=symbol.upper(), day=day, tf=tf)
    return out


def movers(**params: Any) -> dict[str, Any]:
    """Search the day movers index with the agent endpoint's own arguments (``/api/agent/movers``; AGENTS.md
    section 3): ``date_from``, ``date_to``, ``high_min`` (percent points), ``price_max``, ``float_max``, ``sort``,
    ``limit`` ... The answer is the endpoint's: ``rows``, ``summary``, ``coverage``, ``notes``."""
    from agent_desk import movers_read
    return movers_read.search({k: v for k, v in params.items() if v is not None})


def board(day: str, at: str, list_name: str = "gainers", source: str | None = None) -> pd.DataFrame:
    """A past day's Scanner list at ``at`` (ET HH:MM) as the Sim plays it back: recorded when the desk recorded the
    day, else rebuilt from the minute files. ``change_pct`` / ``gap_pct`` in percent points (the store keeps
    fractions). ``df.attrs`` holds the board's source, minute and gap; a day with no board (not recorded and not
    rebuilt: boards cover 1,752 of 2,713 sessions) has ``covered`` False and a ``note`` saying so, never just 0 rows."""
    from leaderboard import playback
    answer = playback.board_at(day, _ns(day, at) / 1e9, source)
    chosen = answer.get("source") or "recorded"
    name = LIST_BOARD.get(chosen, {}).get(list_name)
    rows = (answer.get("boards") or {}).get(name, {}).get("rows", []) if name else []
    frame = pd.DataFrame(sorted(rows, key=lambda r: r.get("rank") or np.inf))
    for column in BOARD_PCT_COLUMNS:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce") * 100.0
    covered, gap = answer.get("covered"), answer.get("gap")
    frame.attrs.update(day=day, at=at, list=list_name, source=chosen, board=name, minute_ts=answer.get("minute_ts"),
                       gap=gap, covered=covered,
                       units="change_pct / gap_pct in percent points (45.6 = +45.6%); prices raw dollars")
    if covered is False or name is None:
        why = (gap or {}).get("reason") or (f"no {list_name} list on a {chosen} day" if name is None else "no board")
        frame.attrs["note"] = (f"no {list_name} board for {day} at {at} ({why}): the day was not recorded by the desk "
                               "and not rebuilt -- data_status lists the days boards cover")
    return frame
