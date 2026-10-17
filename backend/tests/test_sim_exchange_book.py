"""An exchange's own book in Sim replay (ADR 057): the import, the store and the ladder's read.

Every file here is made up -- XYZ and ABC on 2026-09-18, written in the published MBP-10 layouts (DBN 1-3 and the
CSV form) by the builders below -- under a temporary market data root.
"""
from __future__ import annotations

import gzip
import importlib.util
import json
import logging
import sqlite3
import struct
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from sim import exchange_book, exchange_book_import as importer, exchange_book_store as store
from sim import history_depth, history_playback as playback, history_store, massive_import, massive_store
from sim import session_clock as clock
from sim.exchange_book_files import ExchangeBookError

ET = ZoneInfo("America/New_York")
DAY = "2026-09-18"
UNDEF_PRICE = 2**63 - 1
MBP10 = struct.Struct("<BBHIQ" + "qIccBBQiI" + "qqIIII" * 10)
LAST, BAD_BOOK = 0x80, 0x04
NASDAQ, ARCA = 2, 37
XYZ, ABC = 42, 43
TOOL = Path(__file__).resolve().parents[2] / "tools" / "import_exchange_book.py"


def ns(hms: str, us: int = 0) -> int:
    """``hms`` Eastern on DAY, plus ``us`` microseconds, in epoch nanoseconds."""
    return int(datetime.fromisoformat(f"{DAY}T{hms}").replace(tzinfo=ET).timestamp()) * 10**9 + us * 1000


def seconds(at_ns: int) -> float:
    return datetime.fromtimestamp(at_ns // 1000 / 1e6, ET).timestamp()


@dataclass
class Rec:
    at: int
    bids: list = field(default_factory=lambda: [(10.00, 300, 2), (9.99, 500, 3)])
    asks: list = field(default_factory=lambda: [(10.02, 200, 1)])
    flags: int = LAST
    instrument: int = XYZ
    publisher: int = NASDAQ
    symbol: str = "XYZ"


def _level(levels: list, k: int) -> tuple:
    return levels[k] if k < len(levels) else None


def _fixed(level) -> int:
    return UNDEF_PRICE if level is None else round(level[0] * 1e9)


def dbn_record(rec: Rec) -> bytes:
    values = []
    for k in range(10):
        bid, ask = _level(rec.bids, k), _level(rec.asks, k)
        values += [_fixed(bid), _fixed(ask), bid[1] if bid else 0, ask[1] if ask else 0, bid[2] if bid else 0,
                   ask[2] if ask else 0]
    return MBP10.pack(MBP10.size // 4, 0x0A, rec.publisher, rec.instrument, rec.at - 5_000, 0, 0, b"A", b"B",
                      rec.flags, 0, rec.at, 0, 0, *values)


def dbn(records: list[Rec], *, version: int = 2, dataset: str = "XNAS.ITCH", schema: int = 2,
        end: int | None = None, mappings: dict | None = None, extra: bytes = b"") -> bytes:
    width = 22 if version == 1 else 71
    fixed = bytearray(100)
    fixed[0:len(dataset)] = dataset.encode()
    start = ns("00:00") - 4 * 3600 * 10**9                       # the UTC day, as a day file starts
    struct.pack_into("<HQQQ", fixed, 16, schema, start, end if end is not None else ns("20:00"), 0)
    stype_at = 50 if version == 1 else 42
    fixed[stype_at:stype_at + 3] = bytes([1, 0, 0])              # raw symbols in, instrument ids out, no ts_out
    if version != 1:
        struct.pack_into("<H", fixed, 45, width)
    mappings = {"XYZ": [(20260918, 20260919, str(XYZ))], "ABC": [(20260918, 20260919, str(ABC))]} \
        if mappings is None else mappings

    def cstr(text: str) -> bytes:
        return text.encode().ljust(width, b"\0")
    body = bytearray(struct.pack("<I", 0))
    for names in (tuple(mappings), (), ()):
        body += struct.pack("<I", len(names)) + b"".join(cstr(name) for name in names)
    body += struct.pack("<I", len(mappings))
    for raw, intervals in mappings.items():
        body += cstr(raw) + struct.pack("<I", len(intervals))
        for first, last, mapped in intervals:
            body += struct.pack("<II", first, last) + cstr(mapped)
    meta = bytes(fixed) + bytes(body)
    meta += b"\0" * (-len(meta) % 8)
    return b"DBN" + bytes([version]) + struct.pack("<I", len(meta)) + meta + extra + b"".join(map(dbn_record, records))


CSV_LEVELS = [f"{name}_{k:02d}" for k in range(10) for name in ("bid_px", "ask_px", "bid_sz", "ask_sz", "bid_ct",
                                                                   "ask_ct")]


def csv_text(records: list[Rec], *, symbol_column: bool = True, iso: bool = False, pretty: bool = True) -> str:
    head = ["ts_recv", "ts_event", "rtype", "publisher_id", "instrument_id", "action", "side", "depth", "price",
            "size", "flags", "ts_in_delta", "sequence", *CSV_LEVELS] + (["symbol"] if symbol_column else [])

    def when(at: int) -> str:
        if not iso:
            return str(at)
        moment = datetime.fromtimestamp(at // 10**9, ZoneInfo("UTC"))
        return moment.strftime("%Y-%m-%dT%H:%M:%S") + f".{at % 10**9:09d}Z"

    def price(level) -> str:
        if level is None:
            return "" if pretty else str(UNDEF_PRICE)
        return f"{level[0]:.9f}" if pretty else str(round(level[0] * 1e9))
    lines = [",".join(head)]
    for rec in records:
        cells = [when(rec.at), when(rec.at - 5_000), "10", str(rec.publisher), str(rec.instrument), "A", "B", "0",
                 "0", "0", str(rec.flags), "0", "0"]
        for k in range(10):
            bid, ask = _level(rec.bids, k), _level(rec.asks, k)
            cells += [price(bid), price(ask), str(bid[1] if bid else 0), str(ask[1] if ask else 0),
                      str(bid[2] if bid else 0), str(ask[2] if ask else 0)]
        lines.append(",".join(cells + ([rec.symbol] if symbol_column else [])))
    return "\n".join(lines) + "\n"


def day_records() -> list[Rec]:
    """A day of XYZ, with ABC between: what the importer keeps and skips is in each line."""
    return [
        Rec(ns("03:59:00"), bids=[(9.50, 100, 1)], asks=[(9.90, 100, 1)]),                     # before 04:00: dropped
        Rec(ns("03:59:30"), bids=[(9.80, 100, 1)], asks=[(9.95, 100, 1)]),                     # standing at 04:00
        Rec(ns("03:59:40"), flags=0, bids=[(1.00, 1, 1)]),                                    # mid-event: never kept
        Rec(ns("04:00:05"), instrument=ABC, symbol="ABC", bids=[(50.00, 1, 1)]),              # another instrument
        Rec(ns("04:00:05", 250)),                                                              # the default book
        Rec(ns("09:30:00"), flags=0, bids=[(10.10, 1, 1)], asks=[(10.11, 1, 1)]),             # half an event
        Rec(ns("09:30:00"), bids=[(10.10, 400, 4), (10.05, 100, 1)], asks=[(10.12, 300, 2), (10.15, 50, 1)]),
        Rec(ns("15:59:59", 999_999), bids=[(10.40, 100, 1)], asks=[(10.41, 100, 1)]),
        Rec(ns("20:00:00"), bids=[(11.00, 1, 1)], asks=[(11.01, 1, 1)]),                      # from 20:00: dropped
    ]


@pytest.fixture(autouse=True)
def root(tmp_path, monkeypatch):
    base = tmp_path / "market"
    base.mkdir()
    monkeypatch.setenv("NOVA_MARKET_DATA_DIR", str(base))
    monkeypatch.setenv("NOVA_SIM_HISTORY_DIR", str(tmp_path / "history"))
    clock.reset_for_tests()
    playback.clear()
    history_depth.clear()
    exchange_book.reset_for_tests()
    yield base
    clock.reset_for_tests()
    playback.clear()
    history_depth.clear()
    exchange_book.reset_for_tests()


def write(tmp_path: Path, name: str, data: bytes | str) -> Path:
    path = tmp_path / name
    path.write_bytes(data.encode() if isinstance(data, str) else data)
    return path


def chunks(book: str) -> list[dict]:
    db = store.reader()
    try:
        _starts, counts = store.chunk_index(db, book)
        return [store.unpack_chunk(*store.read_chunk(db, book, k)) for k in range(len(counts))]
    finally:
        db.close()


def stored_rows(book: str) -> list[tuple]:
    rows = []
    for columns in chunks(book):
        for i in range(len(columns["ns"])):
            rows.append(tuple(round(v, 9) if isinstance(v, float) and v == v else (None if v != v else v)
                              for v in (columns[name][i] for name in columns)))
    return rows


# ---- the import -------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("version", [1, 2, 3])
def test_a_dbn_file_keeps_the_symbols_whole_events_inside_the_day(tmp_path, version):
    other = bytes([20, 0x17]) + bytes(78)                         # a system record: read past, counted
    path = write(tmp_path, "xyz.dbn", dbn(day_records(), version=version, extra=other))
    report = importer.run(path, "xyz", DAY)
    read, book = report["read"], report["book"]
    assert read["records"] == 10 and read["mbp10"] == 9 and read["other_rtypes"] == {"23": 1}
    assert (read["other_instruments"], read["not_last"], read["before_day"], read["after_day"]) == (1, 2, 1, 1)
    assert read["kept"] == book["events"] == 4 and read["regressions"] == 0
    assert (book["venue"], book["label"], book["dataset"], book["schema"]) == ("NASDAQ", "Nasdaq", "XNAS.ITCH", "mbp-10")
    assert book["known_from_ns"] == ns("04:00") and book["known_to_ns"] == ns("20:00")
    assert book["first_ns"] == ns("03:59:30") and book["last_ns"] == ns("15:59:59", 999_999)
    assert (book["instrument_ids"], book["publisher_id"], book["source_format"], book["dbn_version"]) == \
        ([XYZ], NASDAQ, "dbn", version)
    assert book["id"] == "XYZ|2026-09-18|XNAS.ITCH" and book["compression"] is None


def test_the_csv_form_stores_the_same_book(tmp_path):
    importer.run(write(tmp_path, "xyz.dbn", dbn(day_records())), "XYZ", DAY)
    from_dbn = stored_rows("XYZ|2026-09-18|XNAS.ITCH")
    report = importer.run(write(tmp_path, "xyz.csv", csv_text(day_records())), "XYZ", DAY, dataset="xnas.itch")
    assert stored_rows("XYZ|2026-09-18|XNAS.ITCH") == from_dbn
    # A CSV says nothing of where its data ends: its last event does.
    assert report["book"]["known_to_ns"] == ns("15:59:59", 999_999) + 1
    assert report["book"]["source_format"] == "csv" and report["book"]["dbn_version"] is None


def test_iso_times_and_fixed_point_prices_read_the_same(tmp_path):
    importer.run(write(tmp_path, "plain.csv", csv_text(day_records())), "XYZ", DAY, dataset="XNAS.ITCH")
    plain = stored_rows("XYZ|2026-09-18|XNAS.ITCH")
    importer.run(write(tmp_path, "raw.csv", csv_text(day_records(), iso=True, pretty=False)), "XYZ", DAY,
                 dataset="XNAS.ITCH")
    assert stored_rows("XYZ|2026-09-18|XNAS.ITCH") == plain


def test_gzip_and_zstd_files_read_the_same(tmp_path):
    importer.run(write(tmp_path, "xyz.dbn", dbn(day_records())), "XYZ", DAY)
    plain = stored_rows("XYZ|2026-09-18|XNAS.ITCH")
    report = importer.run(write(tmp_path, "xyz.dbn.gz", gzip.compress(dbn(day_records()))), "XYZ", DAY)
    assert report["book"]["compression"] == "gzip" and stored_rows("XYZ|2026-09-18|XNAS.ITCH") == plain
    zstandard = pytest.importorskip("zstandard")
    packed = zstandard.ZstdCompressor().compress(csv_text(day_records()).encode())
    report = importer.run(write(tmp_path, "xyz.csv.zst", packed), "XYZ", DAY, dataset="XNAS.ITCH")
    assert report["book"]["compression"] == "zstd" and stored_rows("XYZ|2026-09-18|XNAS.ITCH") == plain


def test_a_zstd_file_without_the_package_is_refused_with_what_to_do(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "zstandard", None)
    path = write(tmp_path, "xyz.dbn.zst", b"\x28\xb5\x2f\xfd" + bytes(16))
    with pytest.raises(ExchangeBookError, match="install the zstandard package"):
        importer.run(path, "XYZ", DAY)


def test_a_time_that_runs_backwards_keeps_its_place_and_takes_the_time_before_it(tmp_path):
    records = [Rec(ns("10:00:00"), bids=[(1.0, 1, 1)]), Rec(ns("10:00:02"), bids=[(2.0, 1, 1)]),
               Rec(ns("10:00:01"), bids=[(3.0, 1, 1)])]
    report = importer.run(write(tmp_path, "back.dbn", dbn(records)), "XYZ", DAY)
    assert report["read"]["regressions"] == 1 and report["book"]["regressions"] == 1
    assert list(chunks("XYZ|2026-09-18|XNAS.ITCH")[0]["ns"]) == [ns("10:00:00"), ns("10:00:02"), ns("10:00:02")]
    assert exchange_book.at("XYZ", DAY, seconds(ns("10:00:01")))[0]["bids"][0]["price"] == 1.0
    assert exchange_book.at("XYZ", DAY, seconds(ns("10:00:02")))[0]["bids"][0]["price"] == 3.0


def test_with_no_symbol_named_a_file_of_one_instrument_imports_and_two_are_refused(tmp_path):
    one = [Rec(ns("10:00:00")), Rec(ns("10:00:01"))]
    assert importer.run(write(tmp_path, "one.dbn", dbn(one, mappings={})), "XYZ", DAY)["book"]["events"] == 2
    two = [*one, Rec(ns("10:00:02"), instrument=ABC)]
    path = write(tmp_path, "two.dbn", dbn(two, mappings={}))
    with pytest.raises(ExchangeBookError, match="more than one instrument"):
        importer.run(path, "XYZ", DAY)
    assert importer.run(path, "XYZ", DAY, instrument_id=XYZ)["read"]["other_instruments"] == 1


@pytest.mark.parametrize(("make", "kwargs", "reason"), [
    (lambda: dbn(day_records(), dataset="EQUS.MINI"), {}, "EQUS.MINI is not a single venue"),
    (lambda: dbn(day_records()), {"dataset": "ARCX.PILLAR"}, "The file is XNAS.ITCH, not ARCX.PILLAR"),
    (lambda: dbn(day_records(), schema=0), {}, "MBO file"),
    (lambda: dbn(day_records(), schema=4), {}, "trades file"),
    (lambda: csv_text(day_records()), {}, "A CSV names no dataset"),
    (lambda: "ts_recv,ts_event,rtype,publisher_id,instrument_id,action,side,price,size,channel_id,order_id,flags\n",
     {"dataset": "XNAS.ITCH"}, "MBO file"),
    (lambda: "ts_recv,ts_event,rtype,publisher_id,instrument_id,flags,bid_px_00\n", {"dataset": "XNAS.ITCH"},
     "Not an MBP-10 file"),
    (lambda: dbn([Rec(ns("10:00:00")), Rec(ns("10:00:01"), publisher=ARCA)]), {}, "mixes publishers"),
    (lambda: dbn(day_records(), mappings={"ABC": [(20260918, 20260919, str(ABC))]}), {}, "XYZ is not in this file"),
    (lambda: dbn([Rec(ns("10:00:00"), instrument=ABC)]), {"instrument_id": ABC}, "Instrument 43 is ABC"),
    (lambda: dbn([Rec(ns("03:00:00")), Rec(ns("20:30:00"))]), {}, "No MBP-10 event for XYZ"),
    (lambda: dbn(day_records())[:-100], {}, "cut short"),
    (lambda: bytes(range(200, 256)) * 4, {"dataset": "XNAS.ITCH"}, "neither DBN nor a CSV"),
])
def test_a_refused_import_writes_nothing_and_keeps_the_book_it_would_replace(tmp_path, make, kwargs, reason):
    first = importer.run(write(tmp_path, "good.dbn", dbn(day_records())), "XYZ", DAY)["book"]
    with pytest.raises(ExchangeBookError, match=reason):
        importer.run(write(tmp_path, "bad", make()), "XYZ", DAY, **kwargs)
    assert importer.listing() == [first]


def test_only_a_mapping_of_the_day_names_the_symbols_instrument(tmp_path):
    """An instrument id can belong to another security on another day: a mapping of other dates never stands in."""
    events = [Rec(ns("10:00:00")), Rec(ns("10:00:01"))]                         # instrument 42, on DAY
    elsewhere = {"XYZ": [(20260917, 20260918, str(XYZ))]}
    with pytest.raises(ExchangeBookError, match=r"maps XYZ only on other dates \(2026-09-17 to 2026-09-18"):
        importer.run(write(tmp_path, "old.dbn", dbn(events, mappings=elsewhere)), "XYZ", DAY)
    recycled = write(tmp_path, "recycled.dbn", dbn(events, mappings={**elsewhere,
                                                                     "ABC": [(20260918, 20260919, str(XYZ))]}))
    with pytest.raises(ExchangeBookError, match="maps XYZ only on other dates"):
        importer.run(recycled, "XYZ", DAY)
    with pytest.raises(ExchangeBookError, match="Instrument 42 is ABC in this file on 2026-09-18, not XYZ"):
        importer.run(recycled, "XYZ", DAY, instrument_id=XYZ)
    assert importer.listing() == []
    assert importer.run(recycled, "ABC", DAY)["book"]["instrument_ids"] == [XYZ]    # the day's owner of 42


@pytest.mark.parametrize("damage", ["gzip cut short", "gzip garbled", "zstd cut short"])
def test_a_damaged_compressed_file_is_refused_never_read_short(tmp_path, damage):
    if damage.startswith("zstd"):
        zstandard = pytest.importorskip("zstandard")
        body = zstandard.ZstdCompressor().compress(csv_text(day_records() * 40).encode())
    else:
        body = gzip.compress(dbn(day_records() * 40))
    blob = body[:len(body) // 2] if "cut short" in damage else body[:12] + bytes(64) + body[76:]
    kwargs = {"dataset": "XNAS.ITCH"} if damage.startswith("zstd") else {}
    with pytest.raises(ExchangeBookError, match="cut short|damaged"):
        importer.run(write(tmp_path, "bad.bin", blob), "XYZ", DAY, **kwargs)
    assert importer.listing() == []


def test_a_zstd_file_of_several_frames_reads_whole(tmp_path):
    zstandard = pytest.importorskip("zstandard")
    text = csv_text(day_records())
    head, rows = text.split("\n", 1)
    frames = b"".join(zstandard.ZstdCompressor().compress(part.encode()) for part in (head + "\n", rows))
    report = importer.run(write(tmp_path, "frames.csv.zst", frames), "XYZ", DAY, dataset="XNAS.ITCH")
    assert report["read"]["mbp10"] == 9 and report["book"]["events"] == 4


def test_a_new_import_replaces_the_book_and_the_old_one_reads_until_it_commits(tmp_path, monkeypatch):
    first = importer.run(write(tmp_path, "a.dbn", dbn(day_records())), "XYZ", DAY)["book"]
    seen = []
    monkeypatch.setattr(importer, "_PROGRESS_EVERY", 1)
    second = importer.run(write(tmp_path, "b.dbn", dbn(day_records()[:5])), "XYZ", DAY,
                          progress=lambda _done: seen.append([book["imported_at"] for book in importer.listing()]))
    assert seen and all(row == [first["imported_at"]] for row in seen)           # the old book, while it ran
    assert importer.listing() == [second["book"]] and second["book"]["events"] == 2


def test_list_and_remove(tmp_path):
    importer.run(write(tmp_path, "n.dbn", dbn(day_records())), "XYZ", DAY)
    importer.run(write(tmp_path, "a.dbn", dbn([Rec(ns("10:00:00"), publisher=ARCA)], dataset="ARCX.PILLAR")), "XYZ", DAY)
    assert [book["dataset"] for book in importer.listing(symbol="xyz", day=DAY)] == ["ARCX.PILLAR", "XNAS.ITCH"]
    assert importer.listing(day="2026-09-17") == []
    assert importer.remove("XYZ", DAY, "arcx.pillar") is True and importer.remove("XYZ", DAY, "ARCX.PILLAR") is False
    assert [book["dataset"] for book in importer.listing()] == ["XNAS.ITCH"]


def test_the_import_refuses_a_missing_market_data_folder_rather_than_make_one(tmp_path, monkeypatch):
    missing = tmp_path / "nowhere"
    monkeypatch.setenv("NOVA_MARKET_DATA_DIR", str(missing))
    with pytest.raises(ExchangeBookError, match="No market data folder"):
        importer.run(write(tmp_path, "x.dbn", dbn(day_records())), "XYZ", DAY)
    assert not missing.exists()
    other = tmp_path / "elsewhere" / "books.sqlite3"
    assert importer.run(write(tmp_path, "x.dbn", dbn(day_records())), "XYZ", DAY, where=other)["ok"]
    assert importer.listing(other)[0]["symbol"] == "XYZ"


# ---- the replay's read ------------------------------------------------------------------------------------------
def imported(tmp_path, records: list[Rec] | None = None, **kwargs) -> dict:
    return importer.run(write(tmp_path, "day.dbn", dbn(day_records() if records is None else records, **kwargs)),
                        "XYZ", DAY)["book"]


def test_the_book_at_the_playhead_is_the_last_event_at_or_before_it_never_after(tmp_path):
    imported(tmp_path)

    def bid(hms: str, us: int = 0):
        depth, coverage = exchange_book.at("XYZ", DAY, seconds(ns(hms, us)))
        assert coverage[0]["covered"] is (depth is not None)
        return depth["bids"][0]["price"] if depth else None
    assert bid("03:59:59") is None                                  # before the day: no book, even the standing one
    assert bid("04:00:00") == 9.80                                  # the book standing when the day starts
    assert bid("04:00:05", 249) == 9.80 and bid("04:00:05", 250) == 10.00
    assert bid("09:29:59", 999_999) == 10.00 and bid("09:30:00") == 10.10       # never the half-applied record
    assert bid("19:59:59") == 10.40                                 # a quiet stretch is a book that did not change
    assert bid("20:00:00") is None
    depth, _ = exchange_book.at("XYZ", DAY, seconds(ns("09:30:01")))
    assert depth["ts"] == seconds(ns("09:30:00")) and depth["age_sec"] == pytest.approx(1.0)


def test_every_level_names_its_venue_and_empty_levels_are_left_out(tmp_path):
    imported(tmp_path)
    depth, coverage = exchange_book.at("XYZ", DAY, seconds(ns("09:30:00")))
    assert depth["bids"] == [dict(price=10.10, size=400, orders=4, mm="NASDAQ", exchange="NASDAQ"),
                             dict(price=10.05, size=100, orders=1, mm="NASDAQ", exchange="NASDAQ")]
    assert [level["price"] for level in depth["asks"]] == [10.12, 10.15]
    assert (depth["source"], depth["l1_fallback"], depth["session_id"]) == ("exchange_book", False, None)
    assert depth["venues"] == [dict(venue="NASDAQ", label="Nasdaq", dataset="XNAS.ITCH",
                                    ts=seconds(ns("09:30:00")), maybe_bad_book=False)]
    assert coverage == [dict(venue="NASDAQ", label="Nasdaq", dataset="XNAS.ITCH", known_from=seconds(ns("04:00")),
                             known_to=seconds(ns("20:00")), events=4, imported_at=coverage[0]["imported_at"],
                             covered=True, book_ts=seconds(ns("09:30:00")), maybe_bad_book=False)]


def test_chunk_edges_hold_every_event_even_a_burst_at_one_nanosecond(tmp_path, monkeypatch):
    monkeypatch.setattr(importer, "SIM_EXCHANGE_BOOK_CHUNK_EVENTS", 2)
    burst = [Rec(ns("10:00:00"), bids=[(10.0 + i / 100, 100 + i, 1)]) for i in range(5)]
    book = imported(tmp_path, [Rec(ns("09:00:00"), bids=[(9.0, 1, 1)]), *burst, Rec(ns("10:00:01"), bids=[(11.0, 1, 1)])])
    assert book["chunks"] == 4 and book["events"] == 7
    assert [len(columns["ns"]) for columns in chunks(book["id"])] == [2, 2, 2, 1]
    level = exchange_book.at("XYZ", DAY, seconds(ns("10:00:00")))[0]["bids"][0]
    assert (level["price"], level["size"]) == (10.04, 104)          # the burst's last event, two chunks on
    assert exchange_book.at("XYZ", DAY, seconds(ns("09:59:59", 999_999)))[0]["bids"][0]["price"] == 9.0
    assert exchange_book.at("XYZ", DAY, seconds(ns("10:00:01")))[0]["bids"][0]["price"] == 11.0


def test_the_venues_bad_book_flag_is_said(tmp_path):
    imported(tmp_path, [Rec(ns("10:00:00")), Rec(ns("10:00:01"), flags=LAST | BAD_BOOK)])
    depth, coverage = exchange_book.at("XYZ", DAY, seconds(ns("10:00:02")))
    assert depth["venues"][0]["maybe_bad_book"] is True and coverage[0]["maybe_bad_book"] is True
    assert exchange_book.at("XYZ", DAY, seconds(ns("10:00:00")))[0]["venues"][0]["maybe_bad_book"] is False
    assert importer.listing()[0]["maybe_bad_book"] == 1


def test_two_venues_are_one_montage_each_level_keeping_its_venue(tmp_path):
    imported(tmp_path)
    arca = [Rec(ns("08:00:00"), publisher=ARCA, bids=[(10.11, 50, 1), (10.00, 10, 1)], asks=[(10.13, 70, 2)])]
    importer.run(write(tmp_path, "arca.dbn", dbn(arca, dataset="ARCX.PILLAR")), "XYZ", DAY)
    depth, coverage = exchange_book.at("XYZ", DAY, seconds(ns("09:30:00")))
    assert [(level["price"], level["mm"]) for level in depth["bids"]] == [
        (10.11, "ARCA"), (10.10, "NASDAQ"), (10.05, "NASDAQ"), (10.00, "ARCA")]
    assert [(level["price"], level["mm"]) for level in depth["asks"]] == [
        (10.12, "NASDAQ"), (10.13, "ARCA"), (10.15, "NASDAQ")]
    assert [venue["label"] for venue in depth["venues"]] == ["NYSE Arca", "Nasdaq"]
    assert depth["ts"] == seconds(ns("09:30:00"))                   # the newest event shown
    assert [(row["label"], row["covered"]) for row in coverage] == [("NYSE Arca", True), ("Nasdaq", True)]
    depth, coverage = exchange_book.at("XYZ", DAY, seconds(ns("07:00:00")))
    assert [venue["venue"] for venue in depth["venues"]] == ["NASDAQ"]
    assert [(row["label"], row["covered"], row["book_ts"]) for row in coverage][0] == ("NYSE Arca", False, None)


def test_a_new_import_shows_without_a_restart(tmp_path, monkeypatch):
    assert exchange_book.at("XYZ", DAY, seconds(ns("10:00:00"))) == (None, [])
    imported(tmp_path)
    assert exchange_book.at("XYZ", DAY, seconds(ns("10:00:00")))[0] is None    # the day read a moment ago, held
    monkeypatch.setattr(exchange_book, "_now", lambda: 10**9)                 # ... until its list is read again
    assert exchange_book.at("XYZ", DAY, seconds(ns("10:00:00")))[0]["source"] == "exchange_book"


def test_a_read_never_creates_the_store_and_an_unknown_version_reads_as_no_book(root, tmp_path, caplog):
    assert exchange_book.at("XYZ", DAY, seconds(ns("10:00:00"))) == (None, [])
    assert not store.path().exists()
    store.path().parent.mkdir(parents=True)
    with sqlite3.connect(store.path()) as db:
        db.execute("PRAGMA user_version = 9")
    caplog.set_level(logging.WARNING, logger="sim.exchange_book")
    for _ in range(3):
        assert exchange_book.at("XYZ", DAY, seconds(ns("10:00:00"))) == (None, [])
        exchange_book._days.clear()
    assert sum("cannot be read" in record.message for record in caplog.records) == 1     # once per outage
    with pytest.raises(sqlite3.DatabaseError, match="version 9"):
        importer.run(write(tmp_path, "x.dbn", dbn(day_records())), "XYZ", DAY)


# ---- the replay snapshot ----------------------------------------------------------------------------------------
def select_download(start: str = "04:00", end: str = "09:30") -> dict:
    spec = history_store.window("XYZ", DAY, start, end)
    job = history_store.create(spec, "trades")
    history_store.commit_page(job["id"], spec["start_ts"], [dict(ts=spec["start_ts"] + 1, price=10.0, size=100)],
                              spec["end_ts"], True)
    playback.select(spec)
    clock.set_paused(True)
    return spec


def at_playhead(spec: dict, hms: str) -> dict:
    clock.scrub_to_second(ns(hms) // 10**9 - spec["start_ts"])
    return playback.snapshot("XYZ")


def test_the_snapshot_draws_the_venue_book_and_leaves_the_quote_alone(tmp_path):
    imported(tmp_path)
    spec = select_download()
    snap = at_playhead(spec, "09:00:00")
    assert snap["depth_available"] is True and snap["depth"]["source"] == "exchange_book"
    assert snap["depth"]["bids"][0] == dict(price=10.00, size=300, orders=2, mm="NASDAQ", exchange="NASDAQ")
    assert (snap["bid"], snap["ask"], snap["bid_size"], snap["quote_source"]) == (None, None, None, None)
    assert [(row["venue"], row["covered"]) for row in snap["exchange_books"]] == [("NASDAQ", True)]
    assert playback.snapshot("ABC")["exchange_books"] == []         # another symbol: nothing of XYZ's


def test_outside_a_books_span_the_ladder_is_a_stated_absence(tmp_path):
    imported(tmp_path, [Rec(ns("05:00:00")), Rec(ns("06:00:00"))])
    spec = select_download()
    snap = at_playhead(spec, "04:30:00")
    assert snap["depth"] is None and snap["depth_available"] is False
    assert [(row["covered"], row["book_ts"]) for row in snap["exchange_books"]] == [(False, None)]
    assert snap["exchange_books"][0]["known_from"] == seconds(ns("05:00:00"))


def test_a_covering_venue_book_comes_before_a_recorded_one(tmp_path, monkeypatch):
    imported(tmp_path, [Rec(ns("05:00:00"))])
    spec = select_download()
    recorded = dict(symbol="XYZ", bids=[], asks=[], ts=0.0, age_sec=0.0, l1_fallback=False, session_id="s",
                    source="l2_recorder")
    monkeypatch.setattr(history_depth, "book_at", lambda symbol, t: recorded)
    assert at_playhead(spec, "04:30:00")["depth"]["source"] == "l2_recorder"
    assert at_playhead(spec, "05:30:00")["depth"]["source"] == "exchange_book"


def test_on_a_massive_window_the_venue_book_comes_before_the_nbbo_level(root, tmp_path):
    def gz(dataset: str, text: str) -> None:
        path = root / dataset / DAY[:4] / DAY[5:7] / f"{DAY}.csv.gz"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(gzip.compress(text.encode()))
    at = ns("09:30:00")
    gz("trades_v1", "ticker,conditions,correction,exchange,id,participant_timestamp,price,sequence_number,"
                    f"sip_timestamp,size,tape,trf_id,trf_timestamp\nXYZ,,0,12,1,{at},10.01,1,{at},100,3,0,0\n")
    gz("quotes_v1", "ticker,ask_exchange,ask_price,ask_size,bid_exchange,bid_price,bid_size,conditions,indicators,"
                    f"participant_timestamp,sequence_number,sip_timestamp,tape,trf_timestamp\n"
                    f"XYZ,12,10.03,100,12,9.99,100,1,1,{at},1,{at},3,0\n")
    gz("minute_aggs_v1", "ticker,volume,open,close,high,low,window_start,transactions\n"
                         f"XYZ,100,10.01,10.01,10.01,10.01,{at},1\n")
    spec = massive_import.spec(history_store.window("XYZ", DAY, "09:30", "10:00"))
    job = massive_store.save(dict(massive_store.new_job(spec), status="running"))
    massive_import.run(job["id"])
    playback.select(spec)
    clock.set_paused(True)
    clock.scrub_to_second(600)
    snap = playback.snapshot("XYZ")
    assert snap["depth"]["source"] == "massive_nbbo" and snap["exchange_books"] == []
    imported(tmp_path)
    exchange_book.reset_for_tests()
    snap = playback.snapshot("XYZ")
    assert snap["depth"]["source"] == "exchange_book" and snap["depth"]["bids"][0]["price"] == 10.10
    assert (snap["bid"], snap["ask"], snap["quote_source"]) == (9.99, 10.03, "massive_nbbo")    # still the NBBO's


# ---- the command ------------------------------------------------------------------------------------------------
def test_the_command_imports_lists_removes_and_says_why_it_refuses(tmp_path, capsys):
    spec = importlib.util.spec_from_file_location("import_exchange_book", TOOL)
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    good = write(tmp_path, "xyz.dbn", dbn(day_records()))
    assert tool.main(["import", str(good), "--symbol", "XYZ", "--date", DAY]) == 0
    out = capsys.readouterr().out
    assert "Imported XYZ 2026-09-18 Nasdaq (XNAS.ITCH): 04:00:00-20:00:00 ET, 4 events" in out
    assert tool.main(["list", "--symbol", "XYZ"]) == 0 and "1 imported book(s)" in capsys.readouterr().out
    assert tool.main(["import", str(good), "--symbol", "XYZ", "--date", DAY, "--dataset", "EDGX.PITCH"]) == 1
    assert "Refused: The file is XNAS.ITCH, not EDGX.PITCH" in capsys.readouterr().out
    assert tool.main(["remove", "--symbol", "XYZ", "--date", DAY, "--dataset", "XNAS.ITCH", "--json"]) == 0
    assert '"removed": true' in capsys.readouterr().out
    garbled = write(tmp_path, "garbled.dbn.gz", gzip.compress(dbn(day_records()))[:-20])
    assert tool.main(["import", str(garbled), "--symbol", "XYZ", "--date", DAY, "--json"]) == 1
    answer = json.loads(capsys.readouterr().out)
    assert answer["ok"] is False and "cut short or damaged" in answer["error"]
