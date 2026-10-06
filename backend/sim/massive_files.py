"""The operator's Massive flat files, read for one ticker-day (ADR 046).

Massive serves one gzip CSV per dataset per trading day with every US stock in it,
sorted by ticker: ``<root>/trades_v1/YYYY/MM/YYYY-MM-DD.csv.gz`` (and ``quotes_v1``,
``minute_aggs_v1``). There is no index, so one ticker's rows are read by streaming
the file once, to the end of that ticker's block: a ticker early in the alphabet
costs seconds, one near the end a pass over most of the file (a whole trades day
reads in about a minute, a whole quotes day in about three and a half; measured on
2026-10-02's 3.1 GB and 9.6 GB files).

Nothing is filtered but the window asked for, and nothing is altered: a row keeps
Massive's price, size, nanosecond SIP time, exchange, conditions and correction.
The only conversions are SIP nanoseconds to epoch seconds and an exchange id to its
name. Fields can hold quoted commas (``"14,12,37,41"``), so every row is parsed with
the csv module. Rows are converted chunk by chunk as they stream, so memory holds
the window's rows, never the ticker's whole day of raw text.

A file counts only when it is whole: the downloader writes ``.part`` and renames, so
a day still arriving has no ``.csv.gz`` yet and reads as not on disk.
"""
from __future__ import annotations

import csv
import math
import os
import threading
import zlib
from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from pathlib import Path

from constants_sim import (
    SIM_MASSIVE_DEFAULT_ROOT_WIN, SIM_MASSIVE_DIR_ENV, SIM_MASSIVE_DROPPED_CORRECTIONS, SIM_MASSIVE_EXCHANGES,
    SIM_MASSIVE_MINUTES, SIM_MASSIVE_NO_PRICE_CONDITIONS, SIM_MASSIVE_PRICED_CORRECTIONS, SIM_MASSIVE_QUOTES,
    SIM_MASSIVE_READ_CHUNK, SIM_MASSIVE_TRADES,
)

DATASETS = (SIM_MASSIVE_TRADES, SIM_MASSIVE_QUOTES, SIM_MASSIVE_MINUTES)


class Cancelled(Exception):
    """The import was asked to stop."""


def root() -> Path:
    """``NOVA_MARKET_DATA_DIR``, else the operator's default folder."""
    return Path(os.environ.get(SIM_MASSIVE_DIR_ENV) or SIM_MASSIVE_DEFAULT_ROOT_WIN)


def unavailable_reason() -> str | None:
    """Why the files cannot be read at all, or ``None`` when the folder is there."""
    base = root()
    try:
        if base.is_dir():
            return None
    except OSError as exc:
        return f"The Massive folder {base} cannot be read: {exc}"
    return f"No Massive folder at {base} (set {SIM_MASSIVE_DIR_ENV} to where the flat files are)"


def day_file(dataset: str, day: str) -> Path | None:
    """The whole file of ``dataset`` for the ISO date ``day``, or ``None`` when it is not on disk (yet)."""
    path = root() / dataset / day[:4] / day[5:7] / f"{day}.csv.gz"
    try:
        return path if path.is_file() else None
    except OSError:
        return None


def files_for(day: str) -> dict[str, bool]:
    """Which of the day's datasets are whole on disk."""
    return {name: day_file(name, day) is not None for name in DATASETS}


def ticker_batches(path: Path, ticker: str, *, progress: Callable[[float], None] | None = None,
                   stop: threading.Event | None = None) -> Iterator[tuple[list[str], list[bytes]]]:
    """``(header, lines)`` for each stretch of one ticker's block, in one pass that ends with the block.

    ``progress`` gets the share of the file read so far (0..1); ``stop`` set raises
    ``Cancelled``. A ticker the file does not hold yields nothing.
    """
    key = ticker.strip().upper().encode() + b","
    want = key[:-1]
    size = max(path.stat().st_size, 1)
    decomp = zlib.decompressobj(31)
    header: list[str] | None = None
    tail = b""
    in_block = done = False
    read = 0
    with open(path, "rb") as fh:
        while not done:
            if stop is not None and stop.is_set():
                raise Cancelled()
            chunk = fh.read(SIM_MASSIVE_READ_CHUNK)
            if not chunk:
                break
            read += len(chunk)
            data = tail + decomp.decompress(chunk)
            while decomp.eof and decomp.unused_data:       # a multi-member file: the next member starts fresh
                rest = decomp.unused_data
                decomp = zlib.decompressobj(31)
                data += decomp.decompress(rest)
            if header is None:
                nl = data.find(b"\n")
                if nl < 0:
                    tail = data
                    continue
                header = data[:nl].decode("utf-8").strip().split(",")
                data = data[nl + 1:]
            end = data.rfind(b"\n")
            if end < 0:
                tail = data
                continue
            body, tail = data[:end], data[end + 1:]
            if not in_block:
                if body.startswith(key):
                    start = 0
                else:
                    at = body.find(b"\n" + key)
                    start = at + 1 if at >= 0 else -1
                if start < 0:
                    last = body[body.rfind(b"\n") + 1:]
                    done = last[:last.find(b",")] > want    # sorted by ticker: past it, so the file does not hold it
                    if progress:
                        progress(read / size)
                    continue
                in_block = True
                body = body[start:]
            lines = []
            for line in body.split(b"\n"):
                if not line.startswith(key):
                    done = True
                    break
                lines.append(line)
            if lines:
                yield header, lines
            if progress:
                progress(read / size)
    if in_block and not done and tail.startswith(key):
        yield header or [], [tail.rstrip(b"\r")]          # the file's last line, with no newline after it
    if progress:
        progress(1.0)


def rows(path: Path, ticker: str, convert: Callable[[dict[str, str]], object], *,
         progress: Callable[[float], None] | None = None,
         stop: threading.Event | None = None) -> Iterator[object]:
    """Every row of one ticker, parsed with the csv module and converted; ``None`` results are skipped.

    A line whose field count differs from the header's raises (a damaged or reshaped file), never shifts a column.
    """
    for header, lines in ticker_batches(path, ticker, progress=progress, stop=stop):
        for fields in csv.reader(line.decode("utf-8") for line in lines):
            item = convert(dict(zip(header, fields, strict=True)))
            if item is not None:
                yield item


def _int(value: str | None, default: int = 0) -> int:
    if value in (None, ""):
        return default
    try:
        return int(value)
    except ValueError:
        return int(float(value))


def _price(value: str | None) -> float | None:
    """A quote price, or ``None`` for an empty side (Massive writes 0)."""
    try:
        number = float(value) if value not in (None, "") else 0.0
    except ValueError:
        return None
    return number if math.isfinite(number) and number > 0 else None


def condition_codes(conditions: str | None) -> frozenset[int]:
    return frozenset(int(code) for code in str(conditions or "").split(",") if code.strip().isdigit())


def sets_price(conditions: str | None, correction: int) -> bool:
    """A print that may move the last, a candle or a practice fill (the SIP's rules, ADR 046)."""
    return (correction in SIM_MASSIVE_PRICED_CORRECTIONS
            and condition_codes(conditions).isdisjoint(SIM_MASSIVE_NO_PRICE_CONDITIONS))


def trade(row: dict[str, str], symbol: str) -> dict | None:
    """One trade as a replay print, or ``None`` for a cancel / error record (not a trade)."""
    correction = _int(row.get("correction"))
    if correction in SIM_MASSIVE_DROPPED_CORRECTIONS:
        return None
    ns = _int(row.get("sip_timestamp"))
    conditions = row.get("conditions") or ""
    exchange = _int(row.get("exchange"))
    return dict(ts=ns / 1e9, ns=ns, symbol=symbol, price=float(row["price"]), size=float(row["size"]),
                exchange=SIM_MASSIVE_EXCHANGES.get(exchange, str(exchange)), exchange_id=exchange,
                conditions=conditions, correction=correction, trf_id=_int(row.get("trf_id")),
                sequence=_int(row.get("sequence_number")), tape=_int(row.get("tape")),
                sets_price=sets_price(conditions, correction), unreported=False)


def quote(row: dict[str, str]) -> tuple:
    """One NBBO row: ``(ts, bid, bid_size, bid_x, ask, ask_size, ask_x, conditions, indicators)``.

    A side Massive writes as 0 has no quote and reads ``None`` (its size too).
    """
    bid, ask = _price(row.get("bid_price")), _price(row.get("ask_price"))
    return (_int(row.get("sip_timestamp")) / 1e9,
            bid, float(row.get("bid_size") or 0) if bid is not None else None, _int(row.get("bid_exchange")),
            ask, float(row.get("ask_size") or 0) if ask is not None else None, _int(row.get("ask_exchange")),
            row.get("conditions") or "", row.get("indicators") or "")


def minute(row: dict[str, str]) -> dict:
    """One 1-minute bar in the chart's shape (``t`` UTC ISO, OHLCV)."""
    start = _int(row.get("window_start")) / 1e9
    return dict(t=datetime.fromtimestamp(start, timezone.utc).isoformat().replace("+00:00", "Z"),
                o=float(row["open"]), h=float(row["high"]), l=float(row["low"]), c=float(row["close"]),
                v=float(row["volume"]), n=_int(row.get("transactions")), source="massive")


def minute_start(bar: dict) -> float:
    return datetime.fromisoformat(bar["t"].replace("Z", "+00:00")).timestamp()
