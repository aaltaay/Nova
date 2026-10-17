"""Import one venue's MBP-10 book for a symbol-day into the Sim (ADR 057).

Run by hand (``tools/import_exchange_book.py``), never by the desk and never over the network: it reads one local
file through ``sim.exchange_book_files`` and writes ``sim.exchange_book_store``. What it keeps:

- MBP-10 records of the symbol -- the instrument ids the file's metadata maps it to on the date, else the CSV's
  ``symbol`` column, else ``--instrument-id``, else a file that holds one instrument; never a guess;
- only records that end an exchange event (``F_LAST``): between them the book is half-applied;
- from 04:00 to 20:00 ET of the date, plus the last record before 04:00 -- the book standing when the day starts.

A record stamped earlier than the one before it keeps its place and takes that time (counted in
``regressions``). A book is one publisher's. Every refusal is raised before the transaction commits, so a refused
import writes nothing and leaves the book it would have replaced.
"""
from __future__ import annotations

import re
import time
from array import array
from collections import Counter
from collections.abc import Callable
from datetime import date as Date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from constants_sim import (
    SIM_EXCHANGE_BOOK_CHUNK_EVENTS, SIM_EXCHANGE_BOOK_F_LAST, SIM_EXCHANGE_BOOK_F_MAYBE_BAD_BOOK,
    SIM_EXCHANGE_BOOK_LEVELS, SIM_EXCHANGE_BOOK_SCHEMA_VERSION, SIM_EXCHANGE_BOOK_VENUES, SIM_MASSIVE_DAY_END,
    SIM_MASSIVE_DAY_START, SIM_MASSIVE_DIR_ENV,
)
from sim import exchange_book_store as store
from sim import massive_files
from sim.exchange_book_files import LEVEL_FIELDS, BookFile, Event, ExchangeBookError, Header

ET = ZoneInfo("America/New_York")
_SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9. -]{0,19}")
# The tool says how far it has read every this many MBP-10 records.
_PROGRESS_EVERY = 250_000


def normalized_symbol(symbol: str) -> str:
    symbol = (symbol or "").strip().upper()
    if not _SYMBOL.fullmatch(symbol):
        raise ExchangeBookError("Enter a stock ticker")
    return symbol


def day_bounds(day: str) -> tuple[int, int]:
    """04:00 and 20:00 ET of ``day`` (YYYY-MM-DD), in epoch nanoseconds."""
    try:
        Date.fromisoformat(day)
    except (TypeError, ValueError):
        raise ExchangeBookError(f"{day!r} is not a date (YYYY-MM-DD)") from None
    start, end = (datetime.fromisoformat(f"{day}T{hhmm}").replace(tzinfo=ET) for hhmm in (SIM_MASSIVE_DAY_START,
                                                                                           SIM_MASSIVE_DAY_END))
    return int(start.timestamp()) * 1_000_000_000, int(end.timestamp()) * 1_000_000_000


def venue_of(named: str | None, asked: str | None) -> tuple[str, str, str]:
    """``(dataset, venue code, venue name)``: the file's dataset (a CSV names none) checked against ``--dataset``."""
    named = named.strip().upper() if named else None
    asked = asked.strip().upper() if asked else None
    if named and asked and named != asked:
        raise ExchangeBookError(f"The file is {named}, not {asked}")
    dataset = named or asked
    if not dataset:
        raise ExchangeBookError("A CSV names no dataset: pass --dataset (XNAS.ITCH for Nasdaq, ARCX.PILLAR for "
                                "NYSE Arca, ...)")
    if dataset not in SIM_EXCHANGE_BOOK_VENUES:
        raise ExchangeBookError(f"{dataset} is not a single venue's book Nova knows; it reads "
                                f"{', '.join(sorted(SIM_EXCHANGE_BOOK_VENUES))}")
    code, label = SIM_EXCHANGE_BOOK_VENUES[dataset]
    return dataset, code, label


def _yyyymmdd(value: int) -> str:
    return f"{value // 10000:04d}-{value // 100 % 100:02d}-{value % 100:02d}"


def _instruments(header: Header, symbol: str, day: str, instrument_id: int | None) -> set[int] | None:
    """The instrument ids that are ``symbol`` in this file on ``day``, or None when the file's metadata maps no
    symbol to an instrument id (then the CSV's ``symbol`` column, or a file of one instrument, decides).

    Only a mapping whose dates hold ``day`` counts. An id can belong to another security on another day, so a
    mapping of other dates never stands in for the day's: the import refuses instead (PR #1036 review)."""
    when = int(day.replace("-", ""))
    on_day: dict[str, set[int]] = {}
    other_days: dict[str, list[tuple[int, int]]] = {}
    for raw, intervals in header.mappings.items():
        name = raw.strip().upper()
        for first, last, mapped in intervals:
            if not mapped.isdigit():
                continue
            if first <= when < last:
                on_day.setdefault(name, set()).add(int(mapped))
            else:
                other_days.setdefault(name, []).append((first, last))
    if instrument_id is not None:
        others = sorted(raw for raw, ids in on_day.items() if instrument_id in ids and raw != symbol)
        if others and instrument_id not in on_day.get(symbol, set()):
            raise ExchangeBookError(f"Instrument {instrument_id} is {others[0]} in this file on {day}, not {symbol}")
        return {instrument_id}
    if symbol in on_day:
        return on_day[symbol]
    if symbol in other_days:
        spans = ", ".join(f"{_yyyymmdd(first)} to {_yyyymmdd(last)}" for first, last in sorted(other_days[symbol])[:3])
        raise ExchangeBookError(f"This file maps {symbol} only on other dates ({spans}, the end not included), "
                                f"not {day}: check --date")
    if on_day or other_days:
        raise ExchangeBookError(f"{symbol} is not in this file on {day}; it maps "
                                f"{', '.join(sorted(on_day or other_days)[:8])}")
    return None


class _Chunk:
    """Up to ``SIM_EXCHANGE_BOOK_CHUNK_EVENTS`` kept events as columns, in file order."""

    def __init__(self):
        self.ns, self.flags = array("q"), array("B")
        self.levels = [array("d" if "_px_" in name else "I") for name in LEVEL_FIELDS]

    def add(self, ns: int, event: Event) -> None:
        self.ns.append(ns)
        self.flags.append(event.flags)
        for column, value in zip(self.levels, event.levels, strict=True):
            column.append(value)

    def __len__(self) -> int:
        return len(self.ns)

    def columns(self) -> dict[str, array]:
        return {"ns": self.ns, "flags": self.flags, **dict(zip(LEVEL_FIELDS, self.levels, strict=True))}


class _Copy:
    """The one pass over a file: filters each record, keeps the day's events and writes them chunk by chunk."""

    def __init__(self, writer: store.Writer, symbol: str, ids: set[int] | None, header: Header,
                 day: tuple[int, int]):
        self.writer, self.symbol, self.ids, self.header = writer, symbol, ids, header
        self.day_start, self.day_end = day
        self.counts: Counter = Counter()
        self.seen: set[int] = set()
        self.kept_ids: set[int] = set()
        self.publisher: int | None = None
        self.chunk = _Chunk()
        self.standing: tuple[int, Event] | None = None
        self.last_ns: int | None = None
        self.first_ns: int | None = None
        self.last_kept: int | None = None

    def _ours(self, event: Event) -> bool:
        if self.ids is not None:
            if event.instrument_id not in self.ids:
                return False
            if self.header.has_symbol_column and event.symbol != self.symbol:
                raise ExchangeBookError(f"Instrument {event.instrument_id} is {event.symbol} in this file, "
                                        f"not {self.symbol}")
            return True
        if self.header.has_symbol_column:
            return event.symbol == self.symbol
        self.seen.add(event.instrument_id)
        if len(self.seen) > 1:
            raise ExchangeBookError("The file holds more than one instrument and names none: pass --instrument-id")
        return True

    def take(self, event: Event) -> None:
        if not self._ours(event):
            self.counts["other_instruments"] += 1
            return
        if self.publisher is None:
            self.publisher = event.publisher_id
        elif event.publisher_id != self.publisher:
            raise ExchangeBookError(f"The file mixes publishers {self.publisher} and {event.publisher_id}: a book "
                                    "is one venue's")
        if not event.flags & SIM_EXCHANGE_BOOK_F_LAST:
            self.counts["not_last"] += 1
            return
        ns = event.recv_ns
        if self.last_ns is not None and ns < self.last_ns:
            self.counts["regressions"] += 1
            ns = self.last_ns
        self.last_ns = ns
        if ns < self.day_start:
            if self.standing is not None:
                self.counts["before_day"] += 1
            self.standing = (ns, event)
            return
        if ns >= self.day_end:
            self.counts["after_day"] += 1
            return
        if self.standing is not None:
            self._keep(*self.standing)
            self.standing = None
        self._keep(ns, event)

    def _keep(self, ns: int, event: Event) -> None:
        self.chunk.add(ns, event)
        self.kept_ids.add(event.instrument_id)
        self.counts["kept"] += 1
        if event.flags & SIM_EXCHANGE_BOOK_F_MAYBE_BAD_BOOK:
            self.counts["maybe_bad_book"] += 1
        self.first_ns = ns if self.first_ns is None else self.first_ns
        self.last_kept = ns
        if len(self.chunk) >= SIM_EXCHANGE_BOOK_CHUNK_EVENTS:
            self.flush()

    def flush(self) -> None:
        if len(self.chunk):
            self.writer.put(self.chunk.columns())
            self.chunk = _Chunk()


def _default_store() -> Path:
    root = massive_files.root()
    if not root.is_dir():
        raise ExchangeBookError(f"No market data folder at {root}: set {SIM_MASSIVE_DIR_ENV} to it, or pass --store")
    return store.path()


def run(path: str | Path, symbol: str, day: str, *, dataset: str | None = None, instrument_id: int | None = None,
        where: str | Path | None = None, progress: Callable[[dict], None] | None = None) -> dict:
    """Import ``path``'s book of ``symbol`` on ``day``; the report, or ``ExchangeBookError`` with nothing written."""
    began = time.monotonic()
    symbol = normalized_symbol(symbol)
    bounds = day_bounds(day)
    source = Path(path)
    if not source.is_file():
        raise ExchangeBookError(f"No file at {source}")
    target = Path(where) if where else _default_store()
    with BookFile(source) as book_file:
        header = book_file.header
        if header.schema == "mbo":
            raise ExchangeBookError("This is an MBO file (order by order); Nova reads MBP-10 books only so far")
        if header.schema not in ("mbp-10", None):
            raise ExchangeBookError(f"This is a {header.schema} file; Nova reads MBP-10 books only")
        name, code, label = venue_of(header.dataset, dataset)
        ids = _instruments(header, symbol, day, instrument_id)
        book = store.book_id(symbol, day, name)
        with store.Writer(target, book) as writer:
            copy = _Copy(writer, symbol, ids, header, bounds)
            for n, event in enumerate(book_file.events(), start=1):
                copy.take(event)
                if progress is not None and n % _PROGRESS_EVERY == 0:
                    progress(dict(records=book_file.counts["records"], kept=copy.counts["kept"]))
            counts = copy.counts
            if copy.standing is not None:
                counts["before_day"] += 1
            if not counts["kept"]:
                raise ExchangeBookError(f"No MBP-10 event for {symbol} between {SIM_MASSIVE_DAY_START} and "
                                        f"{SIM_MASSIVE_DAY_END} ET on {day} in this file")
            copy.flush()
            end = header.end_ns if header.end_ns is not None and header.end_ns > copy.last_kept else copy.last_kept + 1
            payload = dict(
                schema_version=SIM_EXCHANGE_BOOK_SCHEMA_VERSION, id=book, symbol=symbol, date=day, dataset=name,
                venue=code, label=label, schema="mbp-10", levels=SIM_EXCHANGE_BOOK_LEVELS,
                known_from_ns=max(bounds[0], copy.first_ns), known_to_ns=min(bounds[1], end),
                first_ns=copy.first_ns, last_ns=copy.last_kept, events=counts["kept"], chunks=writer.chunks,
                maybe_bad_book=counts["maybe_bad_book"], regressions=counts["regressions"],
                instrument_ids=sorted(copy.kept_ids), publisher_id=copy.publisher, source_file=str(source.resolve()),
                source_size=source.stat().st_size, source_format=header.format, compression=header.compression,
                dbn_version=header.dbn_version, imported_at=round(time.time(), 3))
            writer.finish(payload)
        read = dict(records=book_file.counts["records"], mbp10=book_file.counts["mbp10"],
                    other_rtypes={str(rtype): n for rtype, n in sorted(book_file.other_rtypes.items())},
                    **{key: counts[key] for key in ("other_instruments", "not_last", "before_day", "after_day", "kept",
                                                    "regressions", "maybe_bad_book")})
    return dict(ok=True, book=payload, read=read, seconds=round(time.monotonic() - began, 3))


def listing(where: str | Path | None = None, symbol: str | None = None, day: str | None = None) -> list[dict]:
    """Every imported book (newest day first), or those of one symbol and/or day; [] with no store."""
    db = store.reader(Path(where) if where else store.path())
    if db is None:
        return []
    try:
        return store.listing(db, normalized_symbol(symbol) if symbol else None, day)
    finally:
        db.close()


def remove(symbol: str, day: str, dataset: str, where: str | Path | None = None) -> bool:
    """Drop one imported book; False when there was none."""
    day_bounds(day)
    name = dataset.strip().upper()
    return store.remove(Path(where) if where else store.path(), store.book_id(normalized_symbol(symbol), day, name))
