"""Reading one exchange's MBP-10 file for the Sim (ADR 057): DBN or CSV, plain, gzip or zstd.

MBP-10 -- market by price, ten levels -- is one record per change to a venue's book, each carrying the top
ten levels a side after it. The layout is Databento's published one: DBN, its binary encoding (versions 1-3),
or its CSV form, one venue's dataset per file. This module only reads. ``BookFile`` opens a file, reads its
``Header`` and yields each MBP-10 record as an ``Event`` in file order; the importer
(``sim.exchange_book_import``) decides what to keep.

Units are the only conversion: a fixed-point price (1e-9 dollars) becomes dollars, an undefined one
(``INT64_MAX``, or an empty CSV field) NaN -- an empty level, never a zero price -- and an undefined capture time
takes the event's own. Every other value is the file's.

Pure apart from reading the file. Its bytes come through ``sim.exchange_book_streams`` (plain, gzip or zstd), and
a damaged or cut-short file is refused with the reason, never a traceback (PR #1036 review).
"""
from __future__ import annotations

import csv
import io
import math
import re
import struct
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

from constants_sim import SIM_EXCHANGE_BOOK_LEVELS
from sim.exchange_book_streams import READ_BYTES, ExchangeBookError, Prefixed, open_inflated, read_exact, unreadable

__all__ = ["BookFile", "Event", "ExchangeBookError", "Header", "LEVEL_FIELDS", "is_empty_level"]

_DBN_MAGIC = b"DBN"
_DBN_VERSIONS = (1, 2, 3)
# The metadata's fixed part is 100 bytes in every version; version 1 names symbols in 22-byte strings.
_DBN_FIXED_LEN = 100
_DBN_V1_SYMBOL_LEN = 22
_DBN_SCHEMAS = {0: "mbo", 1: "mbp-1", 2: "mbp-10", 3: "tbbo", 4: "trades", 5: "ohlcv-1s", 6: "ohlcv-1m",
                7: "ohlcv-1h", 8: "ohlcv-1d", 9: "definition", 10: "statistics", 11: "status", 12: "imbalance"}
_DBN_MIXED_SCHEMA = 0xFFFF
_RTYPE_MBP10 = 0x0A
_UNDEF_PRICE = 2**63 - 1
_UNDEF_TS = 2**64 - 1
# Record header (length in 4-byte words, rtype, publisher, instrument, ts_event), then MBP-10's body: price, size,
# action, side, flags, depth, ts_recv, ts_in_delta, sequence, and ten levels of (bid_px, ask_px, bid_sz, ask_sz,
# bid_ct, ask_ct).
_MBP10 = struct.Struct("<BBHIQ" + "qIccBBQiI" + "qqIIII" * SIM_EXCHANGE_BOOK_LEVELS)
_LEVELS_AT = 14
_U32_MAX = 2**32 - 1
_NAN = float("nan")

#: An event's levels, in the record's order: for k in 0-9, bid_px, ask_px, bid_sz, ask_sz, bid_ct, ask_ct.
LEVEL_FIELDS = tuple(f"{name}_{k}" for k in range(SIM_EXCHANGE_BOOK_LEVELS)
                     for name in ("bid_px", "ask_px", "bid_sz", "ask_sz", "bid_ct", "ask_ct"))
_CSV_LEVELS = tuple(f"{name}_{k:02d}" for k in range(SIM_EXCHANGE_BOOK_LEVELS)
                    for name in ("bid_px", "ask_px", "bid_sz", "ask_sz", "bid_ct", "ask_ct"))
_CSV_REQUIRED = ("ts_recv", "ts_event", "rtype", "publisher_id", "instrument_id", "flags", *_CSV_LEVELS)
_ISO = re.compile(r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:?\d{2})?")


class Event(NamedTuple):
    """One MBP-10 record. ``symbol`` is the CSV's ``symbol`` column (None in DBN, which maps instrument ids in
    its metadata); ``levels`` are dollars (NaN an empty level) and whole sizes and order counts, ``LEVEL_FIELDS``
    order."""

    recv_ns: int
    publisher_id: int
    instrument_id: int
    symbol: str | None
    flags: int
    levels: list


@dataclass
class Header:
    """What a file says about itself before its first record."""

    format: str
    compression: str | None
    dbn_version: int | None = None
    dataset: str | None = None
    schema: str | None = None
    start_ns: int | None = None
    end_ns: int | None = None
    symbols: tuple[str, ...] = ()
    #: raw symbol -> [(start YYYYMMDD, end YYYYMMDD exclusive, mapped symbol -- an instrument id)].
    mappings: dict[str, list[tuple[int, int, str]]] = field(default_factory=dict)
    has_symbol_column: bool = False


def _price(raw: int) -> float:
    return _NAN if raw == _UNDEF_PRICE else raw / 1e9


def _csv_price(text: str) -> float:
    if not text:
        return _NAN
    if "." in text:
        value = float(text)
        return _NAN if value >= _UNDEF_PRICE / 1e9 else value
    return _price(int(text))


def _count(text: str) -> int:
    value = int(text) if text else 0
    if not 0 <= value <= _U32_MAX:
        raise ExchangeBookError(f"A size or order count of {text} is not one an MBP-10 file can hold")
    return value


def _csv_ns(text: str) -> int:
    """A CSV time: integer nanoseconds, or ISO 8601 with up to nine fractional digits (UTC unless it says)."""
    text = text.strip()
    if text.isdigit():
        return int(text)
    match = _ISO.fullmatch(text)
    if match is None:
        raise ExchangeBookError(f"The time {text!r} is neither nanoseconds nor ISO 8601")
    zone = match.group(3)
    moment = datetime.fromisoformat(match.group(1) + ("+00:00" if zone in (None, "Z") else zone))
    fraction = (match.group(2) or "").ljust(9, "0")
    return int(moment.astimezone(timezone.utc).timestamp()) * 1_000_000_000 + int(fraction or 0)


def _cstr(blob: bytes, at: int, width: int) -> str:
    return blob[at:at + width].split(b"\0", 1)[0].decode("ascii", "replace")


class BookFile:
    """One open MBP-10 file: ``header`` is read on open, ``events()`` yields its MBP-10 records once."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.counts: Counter = Counter()
        self.other_rtypes: Counter = Counter()
        try:
            self._raw = open(self.path, "rb")
        except OSError as exc:
            raise ExchangeBookError(f"The file cannot be opened ({exc})") from exc
        self._inner = None
        try:
            self._inner, compression, self._read_errors = open_inflated(self._raw)
            try:
                head = read_exact(self._inner, 8)
                self._stream = io.BufferedReader(Prefixed(head, self._inner), buffer_size=READ_BYTES)
                if head[:3] == _DBN_MAGIC:
                    self.header = self._dbn_header(head, compression)
                else:
                    self._csv = csv.reader(io.TextIOWrapper(self._stream, encoding="utf-8", newline=""))
                    self.header = self._csv_header(compression)
            except ExchangeBookError:
                raise
            except self._read_errors as exc:
                raise unreadable(exc, "at its start") from exc
        except BaseException:
            self.close()
            raise

    def __enter__(self) -> BookFile:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def close(self) -> None:
        if self._inner is not None and self._inner is not self._raw:
            self._inner.close()
        self._raw.close()

    # -- DBN -------------------------------------------------------------------------------------------
    def _dbn_header(self, head: bytes, compression: str | None) -> Header:
        version = head[3]
        if version not in _DBN_VERSIONS:
            raise ExchangeBookError(f"DBN version {version} is not one Nova reads (it reads 1-3)")
        self._stream.read(8)
        (length,) = struct.unpack_from("<I", head, 4)
        meta = self._stream.read(length)
        if len(meta) < length or length < _DBN_FIXED_LEN + 4:
            raise ExchangeBookError("The file ends inside its DBN header -- it is cut short")
        schema_id, start, end = struct.unpack_from("<HQQ", meta, 16)
        if version == 1:
            width = _DBN_V1_SYMBOL_LEN
        else:
            (width,) = struct.unpack_from("<H", meta, 45)
        header = Header("dbn", compression, dbn_version=version, dataset=_cstr(meta, 0, 16) or None,
                        schema=None if schema_id == _DBN_MIXED_SCHEMA else _DBN_SCHEMAS.get(schema_id, f"#{schema_id}"),
                        start_ns=start, end_ns=None if end in (0, _UNDEF_TS) else end)
        try:
            header.symbols, header.mappings = self._dbn_symbols(meta, width)
        except struct.error as exc:
            raise ExchangeBookError(f"The DBN header's symbol table cannot be read ({exc})") from exc
        return header

    @staticmethod
    def _dbn_symbols(meta: bytes, width: int) -> tuple[tuple[str, ...], dict]:
        (definition,) = struct.unpack_from("<I", meta, _DBN_FIXED_LEN)
        at = _DBN_FIXED_LEN + 4 + definition
        lists = []
        for _ in range(3):  # symbols, partial, not_found
            (count,) = struct.unpack_from("<I", meta, at)
            at += 4
            lists.append(tuple(_cstr(meta, at + i * width, width) for i in range(count)))
            at += count * width
        (count,) = struct.unpack_from("<I", meta, at)
        at += 4
        mappings: dict[str, list[tuple[int, int, str]]] = {}
        for _ in range(count):
            raw = _cstr(meta, at, width)
            (intervals,) = struct.unpack_from("<I", meta, at + width)
            at += width + 4
            rows = mappings.setdefault(raw, [])
            for _ in range(intervals):
                first, last = struct.unpack_from("<II", meta, at)
                rows.append((first, last, _cstr(meta, at + 8, width)))
                at += 8 + width
        if at > len(meta):
            raise struct.error("the symbol table runs past the header")
        return lists[0], mappings

    def _dbn_events(self) -> Iterator[Event]:
        buffer = bytearray()
        offset_base = 0
        while block := self._stream.read(READ_BYTES):
            buffer += block
            at, size_all = 0, len(buffer)
            while at < size_all:
                size = buffer[at] * 4
                if size == 0:
                    raise ExchangeBookError(f"A record of length 0 at byte {offset_base + at} -- the file is damaged")
                if at + size > size_all:
                    break
                self.counts["records"] += 1
                rtype = buffer[at + 1]
                if rtype != _RTYPE_MBP10:
                    self.other_rtypes[rtype] += 1
                elif size < _MBP10.size:
                    raise ExchangeBookError(f"An MBP-10 record of {size} bytes at byte {offset_base + at} -- "
                                            "the file is damaged")
                else:
                    values = _MBP10.unpack_from(buffer, at)
                    levels = list(values[_LEVELS_AT:])
                    for k in range(0, len(levels), 6):
                        levels[k], levels[k + 1] = _price(levels[k]), _price(levels[k + 1])
                    recv = values[11] if values[11] != _UNDEF_TS else values[4]
                    self.counts["mbp10"] += 1
                    yield Event(recv, values[2], values[3], None, values[9], levels)
                at += size
            del buffer[:at]
            offset_base += at
        if buffer:
            raise ExchangeBookError(f"The file ends inside a record ({len(buffer)} bytes left) -- it is cut short")

    # -- CSV -------------------------------------------------------------------------------------------
    def _csv_header(self, compression: str | None) -> Header:
        try:
            names = next(self._csv)
        except StopIteration:
            raise ExchangeBookError("The file is empty") from None
        except UnicodeDecodeError:
            raise ExchangeBookError("The file is neither DBN nor a CSV") from None
        names = [name.strip() for name in names]
        if "order_id" in names and "bid_px_00" not in names:
            raise ExchangeBookError("This is an MBO file (order by order); Nova reads MBP-10 books only so far")
        missing = [name for name in _CSV_REQUIRED if name not in names]
        if missing:
            raise ExchangeBookError(f"Not an MBP-10 file: the CSV has no {', '.join(missing[:3])}"
                                    + (f" and {len(missing) - 3} more columns" if len(missing) > 3 else ""))
        self._index = {name: names.index(name) for name in (*_CSV_REQUIRED, "symbol") if name in names}
        return Header("csv", compression, schema="mbp-10", has_symbol_column="symbol" in names)

    def _csv_events(self) -> Iterator[Event]:
        index = self._index
        cells = [index[name] for name in _CSV_LEVELS]
        prices = {i for i, name in enumerate(_CSV_LEVELS) if "_px_" in name}
        i_recv, i_event, i_rtype = index["ts_recv"], index["ts_event"], index["rtype"]
        i_pub, i_inst, i_flags, i_sym = index["publisher_id"], index["instrument_id"], index["flags"], index.get("symbol")
        for line, row in enumerate(self._csv, start=2):
            if not row:
                continue
            self.counts["records"] += 1
            try:
                rtype = int(row[i_rtype])
                if rtype != _RTYPE_MBP10:
                    self.other_rtypes[rtype] += 1
                    continue
                recv = _csv_ns(row[i_recv]) if row[i_recv] else _csv_ns(row[i_event])
                levels = [_csv_price(row[c]) if i in prices else _count(row[c]) for i, c in enumerate(cells)]
                flags = int(row[i_flags])
                if not 0 <= flags <= 0xFF:
                    raise ExchangeBookError(f"flags {flags} do not fit MBP-10's one byte")
                event = Event(recv, int(row[i_pub]), int(row[i_inst]),
                              row[i_sym].strip().upper() if i_sym is not None else None, flags, levels)
            except (IndexError, ValueError) as exc:
                if isinstance(exc, ExchangeBookError):
                    raise ExchangeBookError(f"Line {line}: {exc}") from exc
                raise ExchangeBookError(f"Line {line} is not an MBP-10 row ({exc})") from exc
            self.counts["mbp10"] += 1
            yield event

    def events(self) -> Iterator[Event]:
        """Each MBP-10 record in file order. ``counts`` and ``other_rtypes`` tally what was read so far."""
        try:
            yield from (self._dbn_events() if self.header.format == "dbn" else self._csv_events())
        except ExchangeBookError:
            raise
        except self._read_errors as exc:
            raise unreadable(exc, f"after {self.counts['records']:,} records") from exc


def is_empty_level(price: float, size: int) -> bool:
    """An empty book level: no price, or nothing resting at it."""
    return math.isnan(price) or size <= 0
