"""The operator's Massive flat files, read for one ticker-day (ADR 046).

Massive serves one gzip CSV per dataset per trading day with every US stock in it,
sorted by ticker: ``<root>/trades_v1/YYYY/MM/YYYY-MM-DD.csv.gz`` (and ``quotes_v1``,
``minute_aggs_v1``). Massive ships no index. The first read of a day file streams it
through zlib from the start to the end of the ticker's block (an early ticker costs
seconds, one near the end most of the file: VEEA on 2026-09-09 sat 91% into a 7.3 GB
quotes file), into one reused buffer. Once the import is done, ``massive_index``
builds the file's index; every later read of that file (any ticker that day, any
window) enters it at the ticker and inflates little else (``DayRead``).

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
import logging
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
    SIM_MASSIVE_READ_CHUNK, SIM_MASSIVE_REPEAT_CONDITIONS, SIM_MASSIVE_TRADES,
)
from sim import massive_index

logger = logging.getLogger(__name__)
DATASETS = (SIM_MASSIVE_TRADES, SIM_MASSIVE_QUOTES, SIM_MASSIVE_MINUTES)
_said_no_index = threading.Event()


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


class _Zlib:
    """A day file inflated by zlib behind ``readinto``: the read of a file that has no index yet."""

    def __init__(self, path: Path):
        self._fh = open(path, "rb")
        self._decomp = zlib.decompressobj(31)
        self._pending = memoryview(b"")
        self.consumed = 0                   # compressed bytes read: the progress

    def readinto(self, out) -> int:
        while not len(self._pending):
            chunk = self._fh.read(SIM_MASSIVE_READ_CHUNK)
            if not chunk:
                return 0
            self.consumed += len(chunk)
            data = self._decomp.decompress(chunk)
            while self._decomp.eof and self._decomp.unused_data:   # a multi-member file: the next member starts fresh
                rest = self._decomp.unused_data
                self._decomp = zlib.decompressobj(31)
                data += self._decomp.decompress(rest)
            self._pending = memoryview(data)
        n = min(len(out), len(self._pending))
        out[:n] = self._pending[:n]
        self._pending = self._pending[n:]
        return n

    def close(self) -> None:
        self._fh.close()


def _past(buf: bytearray, lo: int, end: int, want: bytes) -> bool:
    """Whether the stretch's lines ``[lo, end)`` have passed ``want``'s block: its last PLAIN ticker sorts after it.

    Only a plain ticker can say so (``massive_index.plain``): a trades file puts ``AApB`` right after ``AA`` and
    before ``AAAP``, so a stretch ending on ``AApB`` is not past ``AAAP``. Every block, plain or not, lies before
    each plain ticker that sorts after it, in either order the files use. A stretch with no plain line says nothing.
    """
    stop = end
    while stop > lo:
        last = buf.rfind(b"\n", lo, stop) + 1 or lo
        comma = buf.find(b",", last, stop)
        ticker = bytes(buf[last:comma if comma >= 0 else stop])
        if massive_index.plain(ticker):
            return ticker > want
        stop = last - 1
    return False


def _carry(buf: bytearray, frm: int, filled: int) -> int:
    """Move ``buf[frm:filled]`` (a partial last line) to the front; its length."""
    n = filled - frm
    if n > 0 and frm > 0:
        buf[:n] = buf[frm:filled]
    return max(n, 0)


class DayRead:
    """One day file read for one ticker: through the file's saved index when it has one, else streamed.

    With the index (``massive_index``), the read finds the block in the index's map of the file, enters the file at
    the seek point before it and inflates the block and little else. Without it, zlib streams the file from the
    start to the end of the block, as it always did; the import then builds the index (``massive_index.build``),
    so the next read of that file -- any ticker, any window -- is quick.
    """

    def __init__(self, path: Path, ticker: str):
        self.path, self.ticker = path, ticker
        self.key = ticker.strip().upper().encode() + b","
        self.stream = None
        self.indexed = False                # entered through a saved index

    def __enter__(self) -> DayRead:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        stream, self.stream = self.stream, None
        if stream is not None:
            stream.close()

    def batches(self, progress: Callable[[float], None] | None = None,
                stop: threading.Event | None = None) -> Iterator[tuple[list[str], list[bytes]]]:
        """``(header, lines)`` for each stretch of the ticker's block; a ticker the file does not hold yields nothing.

        ``progress`` gets the share read (0..1): of the file, or through an index of the stretch the block is in;
        ``stop`` set raises ``Cancelled``.
        """
        saved = massive_index.load(self.path, root()) if massive_index.available() else None
        entered = self._enter(saved) if saved is not None else None
        if entered is None:
            if not massive_index.available() and not _said_no_index.is_set():
                _said_no_index.set()
                logger.warning("indexed_gzip is not installed: Massive day files are always streamed from the start "
                               "(pip install -r backend/requirements.txt)")
            size = max(self.path.stat().st_size, 1)
            self.stream = _Zlib(self.path)
            yield from self._scan(None, lambda: self.stream.consumed / size, progress, stop)
        else:
            start, end = entered
            span = max(end - start, 1)
            yield from self._scan(saved.header, lambda: (self.stream.tell() - start) / span, progress, stop)
        if progress:
            progress(1.0)

    def _enter(self, saved: massive_index.Saved) -> tuple[int, int] | None:
        """Open the file through its saved index at the ticker's stretch: ``(start, end)``, or ``None`` (logged) when the
        index will not open -- the file is then streamed, and the import builds its index again over the bad one."""
        stream = None
        try:
            stream = massive_index.open_file(self.path, saved.seek_points)
            start, end = massive_index.locate(saved.marks, self.key[:-1], saved.body, saved.length)
            stream.seek(start)
        except Exception as exc:                        # a damaged or foreign index never fails the read
            logger.warning("Massive index for %s could not be used (%s); the file is streamed and its index rebuilt",
                           self.path, exc)
            if stream is not None:
                stream.close()
            return None
        self.stream, self.indexed = stream, True
        return start, end

    def rows(self, convert: Callable[[dict[str, str]], object], *, progress: Callable[[float], None] | None = None,
             stop: threading.Event | None = None) -> Iterator[object]:
        """Every row of the ticker, parsed with the csv module and converted; ``None`` results are skipped.

        A line whose field count differs from the header's raises (a damaged or reshaped file), never shifts a column.
        """
        for header, lines in self.batches(progress, stop):
            for fields in csv.reader(line.decode("utf-8") for line in lines):
                item = convert(dict(zip(header, fields, strict=True)))
                if item is not None:
                    yield item

    def _scan(self, header: list[str] | None, fraction: Callable[[], float], progress, stop):
        """The block's lines from the stream (at a line start), read into one reused buffer; ends with the block."""
        key = self.key
        want = key[:-1]
        buf = bytearray(max(int(SIM_MASSIVE_READ_CHUNK), 1))
        held = 0
        in_block = False
        while True:
            if stop is not None and stop.is_set():
                raise Cancelled()
            if held == len(buf):                            # a line longer than the buffer: make room
                buf.extend(bytes(len(buf)))
            n = self.stream.readinto(memoryview(buf)[held:])
            if not n:
                break
            filled, lo = held + n, 0
            if header is None:
                nl = buf.find(b"\n", 0, filled)
                if nl < 0:
                    held = filled
                    continue
                header = bytes(buf[:nl]).decode("utf-8").strip().split(",")
                lo = nl + 1
            end = buf.rfind(b"\n", lo, filled)
            if end < 0:
                held = _carry(buf, lo, filled)
                continue
            if not in_block:
                if buf.startswith(key, lo):
                    start = lo
                else:
                    at = buf.find(b"\n" + key, lo, end)
                    start = at + 1 if at >= 0 else -1
                if start < 0:
                    if progress:
                        progress(fraction())
                    if _past(buf, lo, end, want):
                        return                              # sorted by ticker: past it, so the file does not hold it
                    held = _carry(buf, end + 1, filled)
                    continue
                in_block, lo = True, start
            lines = memoryview(buf)[lo:end].tobytes().split(b"\n")
            done = not lines[-1].startswith(key)            # sorted: the block ends in this stretch
            if done:
                lines = lines[:next(i for i, line in enumerate(lines) if not line.startswith(key))]
            if lines:
                yield header, lines
            if progress:
                progress(fraction())
            if done:
                return
            held = _carry(buf, end + 1, filled)
        if held and buf.startswith(key, 0, held):
            yield header or [], [bytes(buf[:held]).rstrip(b"\r")]   # the file's last line, with no newline after it


def ticker_batches(path: Path, ticker: str, *, progress: Callable[[float], None] | None = None,
                   stop: threading.Event | None = None) -> Iterator[tuple[list[str], list[bytes]]]:
    """``(header, lines)`` for each stretch of one ticker's block (``DayRead.batches``; no index is written)."""
    with DayRead(path, ticker) as read:
        yield from read.batches(progress, stop)


def rows(path: Path, ticker: str, convert: Callable[[dict[str, str]], object], *,
         progress: Callable[[float], None] | None = None,
         stop: threading.Event | None = None) -> Iterator[object]:
    """Every row of one ticker, parsed and converted (``DayRead.rows``; no index is written)."""
    with DayRead(path, ticker) as read:
        yield from read.rows(convert, progress=progress, stop=stop)


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


def repeats_a_print(conditions: str | None) -> bool:
    """An official open / close or corrected-close record: a repeat of an auction print already on the tape.

    IBKR's live tape has no such records (the opening cross prints once), so a replay leaves them out, and no
    volume counts them."""
    return not condition_codes(conditions).isdisjoint(SIM_MASSIVE_REPEAT_CONDITIONS)


def counts_volume(conditions: str | None, correction: int) -> bool:
    """A print the consolidated tape counts in volume: a regular trade or a correction record (0 / 12), never a
    repeat record, a cancelled or corrected original (1 / 7 / 8) or a cancel / error record (10 / 11)."""
    return correction in SIM_MASSIVE_PRICED_CORRECTIONS and not repeats_a_print(conditions)


def trade(row: dict[str, str], symbol: str) -> dict | None:
    """One trade as a replay print, or ``None`` for a cancel / error record or a repeat record (not a trade)."""
    correction = _int(row.get("correction"))
    conditions = row.get("conditions") or ""
    if correction in SIM_MASSIVE_DROPPED_CORRECTIONS or repeats_a_print(conditions):
        return None
    ns = _int(row.get("sip_timestamp"))
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
