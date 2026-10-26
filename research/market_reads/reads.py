"""One stock-day out of the Massive files as a table, and the day movers index and past-day boards without the API.

Every row of a file comes back as delivered (Massive's columns, its nanosecond SIP times) plus ``time_et``; nothing is
adjusted for splits, and nothing is filtered but the window asked for -- except the bars built from trades, which
follow the Sim's own print rules (``sim.massive_files.trade`` / ``sets_price``). The reads go through
``sim.massive_files.DayRead``: about a second on a day whose index is built, minutes on one whose index is not.
"""
from __future__ import annotations

import functools
import io
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from market_reads import REPO  # noqa: F401  (puts backend/ on sys.path)

from constants_sim import (
    SIM_MASSIVE_MINUTES,
    SIM_MASSIVE_PRICED_CORRECTIONS,
    SIM_MASSIVE_QUOTES,
    SIM_MASSIVE_TRADES,
)
from sim import massive_files, massive_index

from market_reads import read_cache

ET = ZoneInfo("America/New_York")
TF_UNITS = {"s": 1, "m": 60, "h": 3600}
GAPS_LISTED = 50         # runs of missing bars ``meta.gaps`` lists (the longest); the counts cover every run
BOARD_PCT_COLUMNS = ("change_pct", "gap_pct")   # the board store keeps fractions; answered in percent points
TEXT_COLUMNS = {"ticker": str, "conditions": str, "indicators": str, "id": str}
# Only an empty field is missing: pandas' default NA strings ("NA", "NULL", "N/A", ...) are real tickers.
CSV_NA = {"keep_default_na": False, "na_values": [""]}
TIME_COLUMN = {SIM_MASSIVE_TRADES: "sip_timestamp", SIM_MASSIVE_QUOTES: "sip_timestamp",
               SIM_MASSIVE_MINUTES: "window_start"}
# The board each list reads on a recorded day and on a rebuilt one (a rebuilt day's Gainers is its market board).
LIST_BOARD = {
    "recorded": {"gainers": "gainers", "losers": "losers", "gappers": "gappers", "afterhours": "afterhours",
                 "large_cap": "large_cap"},
    "reconstructed": {"gainers": "market", "losers": "losers", "gappers": "gappers", "afterhours": "afterhours"},
}


def _ns(day: str, hhmm: str) -> int:
    hh, mm = (int(part) for part in hhmm.split(":"))
    d = date.fromisoformat(day)
    return int(datetime(d.year, d.month, d.day, hh, mm, tzinfo=ET).timestamp()) * 10**9


def _parse_day(path, symbol: str) -> tuple[pd.DataFrame, list[str], bool]:
    """``symbol``'s whole day in the file as parsed (no window, no ``time_et``), its header, and whether the read went
    through the file's index. What ``read_cache`` keeps: its fingerprint covers this function's source."""
    header: list[str] | None = None
    lines: list[bytes] = []
    with massive_files.DayRead(path, symbol) as read:
        for head, batch in read.batches():
            header = head or header
            lines.extend(batch)
        indexed = read.indexed
    if not lines:
        return pd.DataFrame(columns=header or []), header or [], indexed
    text = (",".join(header or []) + "\n").encode() + b"\n".join(lines) + b"\n"
    frame = pd.read_csv(io.BytesIO(text), dtype={k: v for k, v in TEXT_COLUMNS.items() if k in (header or [])},
                        **CSV_NA)
    return frame, header or [], indexed


def _probe(lines: list[bytes], header: list[str]):
    """A stretch's non-text columns as pyarrow reads them (a real CSV parser: a quoted comma is no separator), or
    ``None`` when it cannot read the stretch line for line."""
    import pyarrow as pa
    import pyarrow.csv as pacsv
    try:
        table = pacsv.read_csv(io.BytesIO(b"\n".join(lines) + b"\n"),
                               read_options=pacsv.ReadOptions(column_names=header),
                               convert_options=pacsv.ConvertOptions(
                                   include_columns=[name for name in header if name not in TEXT_COLUMNS]))
    except pa.ArrowInvalid:
        return None
    return table if table.num_rows == len(lines) else None


def _parse_window(path, symbol: str, column: str, lo: int | None,
                  hi: int | None) -> tuple[pd.DataFrame, bool] | None:
    """``symbol``'s rows with ``column`` in ``[lo, hi)`` exactly as ``_parse_day`` then the window would give them,
    with only those lines parsed by pandas; ``None`` when that cannot be vouched for (the caller parses the day).

    pyarrow reads the block's non-text columns first: their times pick the lines, and each column's type and gaps
    over the whole block say which dtype the whole-day parse gives -- a whole-number column with a gap or a fraction
    anywhere that day is float64 there, so the window's is cast to it. A window holding no row, a time that is not a
    whole number on every line, or a non-text column that is not a number somewhere that day takes the whole-day
    way. Nothing about row order is assumed."""
    import pyarrow as pa
    header: list[str] | None = None
    kept: list[bytes] = []
    floats: set[str] = set()
    other: set[str] = set()
    with massive_files.DayRead(path, symbol) as read:
        for head, batch in read.batches():
            header = head or header
            table = _probe(batch, header)
            if table is None or column not in table.column_names:
                return None
            times = table.column(column)
            if not pa.types.is_integer(times.type) or times.null_count:
                return None
            for name, values in zip(table.column_names, table.columns, strict=True):
                if pa.types.is_floating(values.type) or values.null_count:
                    floats.add(name)
                elif not pa.types.is_integer(values.type):
                    other.add(name)
            times = times.to_numpy()
            inside = np.ones(len(batch), dtype=bool)
            if lo is not None:
                inside &= times >= lo
            if hi is not None:
                inside &= times < hi
            kept.extend(batch[i] for i in np.flatnonzero(inside))
        indexed = read.indexed
    if header is None:                       # the file does not hold the symbol: _parse_day's empty frame
        return pd.DataFrame(columns=[]), indexed
    if other or not kept:
        return None
    text = (",".join(header) + "\n").encode() + b"\n".join(kept) + b"\n"
    frame = pd.read_csv(io.BytesIO(text), dtype={k: v for k, v in TEXT_COLUMNS.items() if k in header}, **CSV_NA)
    for name in floats & set(frame.columns):
        if pd.api.types.is_integer_dtype(frame[name].dtype):
            frame[name] = frame[name].astype("float64")
    return frame, indexed


@functools.cache
def _reader() -> str:
    """The read cache's key for the code that finds and parses the rows (any change to it is a miss)."""
    return read_cache.fingerprint(_parse_day, massive_files, massive_index, TEXT_COLUMNS, CSV_NA)


def read_file(dataset: str, symbol: str, day: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """``symbol``'s rows of ``dataset`` on ``day`` (ET ``start`` <= time < ``end``), every column as delivered.

    ``df.attrs`` says whether the read went through the file's index (``indexed``) and how long it took. A symbol-day
    read before comes out of the read cache (``read_cache``) when it is on: the same frame, without the unzip. A
    window the cache does not hold parses only the window's lines (``_parse_window``; the cache keeps whole days, so
    that read is not saved), so a few minutes of a busy day cost those minutes, not the day.
    """
    path = massive_files.day_file(dataset, day)
    if path is None:
        raise LookupError(f"no {dataset} file for {day} under {massive_files.root()}")
    t0 = datetime.now()
    column = TIME_COLUMN[dataset]
    cached = read_cache.load(dataset, symbol, day, path, _reader()) if read_cache.root() else None
    window = None
    if cached is None and (start or end):
        window = _parse_window(path, symbol, column, _ns(day, start) if start else None,
                               _ns(day, end) if end else None)
    if cached is not None:
        frame, indexed = cached
    elif window is not None:
        frame, indexed = window
    else:
        before = read_cache.source_identity(path) if read_cache.root() else None
        frame, header, indexed = _parse_day(path, symbol)
        if before is not None:
            read_cache.save(dataset, symbol, day, path, _reader(), before, frame, header, indexed)
    if len(frame):
        if start:
            frame = frame[frame[column] >= _ns(day, start)]
        if end:
            frame = frame[frame[column] < _ns(day, end)]
        frame = frame.reset_index(drop=True)
        frame.insert(0, "time_et", pd.to_datetime(frame[column], unit="ns", utc=True).dt.tz_convert(ET))
    frame.attrs.update(dataset=dataset, symbol=symbol.upper(), day=day, indexed=indexed,
                       seconds=round((datetime.now() - t0).total_seconds(), 2), file=str(path))
    return frame


def trades(symbol: str, day: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """Every trade, plus ``sets_price``: the print may move the last or a candle (the SIP's rules, ADR 046)."""
    frame = read_file(SIM_MASSIVE_TRADES, symbol, day, start, end)
    if len(frame):
        frame["sets_price"] = sets_price(frame["conditions"], frame["correction"])
    return frame


def sets_price(conditions: pd.Series, correction: pd.Series) -> np.ndarray:
    """``massive_files.sets_price`` for every row, asked once per distinct (conditions, correction) pair: a day holds
    a few hundred pairs and millions of prints. A missing conditions field reads as none, a missing correction as 0."""
    text_codes, texts = pd.factorize(conditions, use_na_sentinel=True)          # missing -> -1
    fix_codes, fixes = pd.factorize(correction.fillna(0).to_numpy().astype(np.int64))   # int(k): toward zero
    width = max(len(fixes), 1)
    pair_codes, pairs = pd.factorize((text_codes.astype(np.int64) + 1) * width + fix_codes)
    answers = np.zeros(len(pairs), dtype=bool)
    for n, pair in enumerate(int(v) for v in pairs):
        text = texts[pair // width - 1] if pair // width else ""
        answers[n] = massive_files.sets_price(text if isinstance(text, str) else "", int(fixes[pair % width]))
    return answers[pair_codes]


def repeats_a_print(conditions: pd.Series) -> np.ndarray:
    """True for an official open / close or corrected-close record: a repeat of an auction print, no volume of its
    own. Asked once per distinct conditions string."""
    text_codes, texts = pd.factorize(conditions, use_na_sentinel=True)          # missing -> -1
    answers = np.array([massive_files.repeats_a_print(text) for text in texts] + [False], dtype=bool)
    return answers[text_codes]                                                   # -1 picks the trailing False


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


def _missing(buckets: np.ndarray, step: int, day: str, start: str | None, end: str | None) -> np.ndarray:
    """Start (epoch seconds) of every bucket the window holds a slot for and the read has no bar in. The window is the
    asked ``start`` .. ``end`` (exclusive), else the first .. last bar."""
    low = _ns(day, start) // 10**9 if start else int(buckets[0])
    high = _ns(day, end) // 10**9 if end else int(buckets[-1]) + step
    return np.setdiff1d(np.arange(low // step * step, (high - 1) // step * step + 1, step), buckets)


def _gap_meta(missing: np.ndarray, step: int) -> dict[str, Any]:
    """``meta.gaps``: the runs of consecutive missing buckets as ET ``first_et`` / ``last_et`` (both inclusive) and
    ``buckets``, in time order, the longest ``GAPS_LISTED`` when there are more (``gaps_truncated``)."""
    rule = ("a gap is a bucket with no trade inside the window (a halt, or a quiet stretch; the halts tool lists "
            "halts); no price is guessed for it. fill_gaps=true adds a row per gap")
    if not len(missing):
        return {"gaps": [], "gap_runs": 0, "gap_buckets": 0, "gaps_truncated": False, "gap_rule": rule}
    breaks = np.flatnonzero(np.diff(missing) != step) + 1
    firsts, lasts = missing[np.r_[0, breaks]], missing[np.r_[breaks - 1, len(missing) - 1]]
    sizes = (lasts - firsts) // step + 1
    kept = np.sort(np.argsort(-sizes, kind="stable")[:GAPS_LISTED])
    form = "%H:%M" if step % 60 == 0 else "%H:%M:%S"
    gaps = [{"first_et": datetime.fromtimestamp(int(firsts[i]), ET).strftime(form),
             "last_et": datetime.fromtimestamp(int(lasts[i]), ET).strftime(form), "buckets": int(sizes[i])}
            for i in kept]
    return {"gaps": gaps, "gap_runs": int(len(firsts)), "gap_buckets": int(len(missing)),
            "gaps_truncated": bool(len(firsts) > GAPS_LISTED), "gap_rule": rule}


def _filled(out: pd.DataFrame, missing: np.ndarray) -> pd.DataFrame:
    """``out`` with a row per missing bucket: no prices, no volume, ``filled`` true. A price is never carried over."""
    every = np.union1d(out["bucket"].to_numpy(), missing)
    new = ~np.isin(every, out["bucket"].to_numpy())
    rows = out.set_index("bucket").reindex(every)
    for column in ("volume", "transactions"):
        rows[column] = rows[column].fillna(0).astype(out[column].dtype)
    rows["filled"] = new
    return rows.reset_index()


def bars(symbol: str, day: str, tf: str = "1m", start: str | None = None, end: str | None = None,
         fill_gaps: bool = False) -> pd.DataFrame:
    """OHLCV bars. Minutes (``1m``, ``5m``, ...) from the minute file, as delivered and summed; seconds (``10s``)
    from the trades by the Sim's rules: only a price-setting print sets open / high / low / close, and the volume
    is what the consolidated tape counts (``massive_files.counts_volume``): every regular trade and correction
    record, never a cancel / error record, a cancelled or corrected original, or an official open / close or
    corrected-close record, which repeats an auction print. A bar with no price-setting print has no prices (its
    volume stands).

    A bucket with no trade has no row. ``df.attrs['gaps']`` says where they are (``_gap_meta``); ``fill_gaps`` adds a
    row for each, with no prices, zero volume and ``filled`` true (#1086)."""
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
        kept = prints[prints["correction"].fillna(0).astype(int).isin(SIM_MASSIVE_PRICED_CORRECTIONS)
                      & ~repeats_a_print(prints["conditions"])].copy()
        kept["bucket"] = kept["sip_timestamp"] // (step * 10**9) * step
        priced = kept[kept["sets_price"]]
        volume = kept.groupby("bucket")["size"].agg(["sum", "count"]).rename(columns={"sum": "volume",
                                                                                    "count": "transactions"})
        ohlc = priced.groupby("bucket")["price"].agg(open="first", high="max", low="min", close="last")
        out = volume.join(ohlc, how="left")[["open", "high", "low", "close", "volume", "transactions"]]
    out = out.reset_index()
    missing = None
    if len(out):                 # every print of a seconds window can be a discarded cancel / error: no bar, no gaps
        missing = _missing(out["bucket"].to_numpy(), step, day, start, end)
        if fill_gaps:
            out = _filled(out, missing)
    out.insert(0, "time_et", pd.to_datetime(out.pop("bucket"), unit="s", utc=True).dt.tz_convert(ET))
    out.attrs.update(symbol=symbol.upper(), day=day, tf=tf, **({} if missing is None else _gap_meta(missing, step)))
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
    rebuilt: boards cover about 1,750 of 2,713 sessions) has ``covered`` False and a ``note`` saying so, never just 0 rows."""
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
