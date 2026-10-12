"""Seek indexes for the Massive day files: one ticker's block without inflating the tickers before it (ADR 046).

A day file is one gzip stream of every US stock sorted by ticker, with no index, so a
ticker late in the alphabet costs most of the file (2026-09-09: VEEA's 238 quotes sat
behind 33 GB of other tickers' quotes text, and its import took 183 s). ``build`` reads
a day file once, start to end, through indexed_gzip (zlib's zran method: one 32 KB
window of text per seek point, so its memory stays flat) and saves two things here:
the seek points, where the deflate stream can be entered again (every
``SIM_MASSIVE_INDEX_SPACING`` of text), and a map of the file -- the offset and ticker of
one line in every ``SIM_MASSIVE_READ_CHUNK`` of text. A later read (``massive_files.
DayRead``) finds its ticker in the map without reading anything, enters the file at the
seek point before it and inflates the block and at most one spacing and one stretch
before it: a seek or two on the hard drive, however busy it is.

An import builds the indexes of the files it read without one after its job is
complete (``massive_read.run``), so the first stock of a day costs what it always did
and every later read of that day is quick. One build per file at a time, across
processes (``<index>.lock``, rewritten while it builds).

Persisted state (persisted-state.mdc). Owner: this module, the only reader and writer
of ``<root>/sim/index/<dataset>/YYYY/MM/YYYY-MM-DD.csv.gz.idx``. Its first line is a
JSON header -- ``schema_version``, the day file's ``size`` and ``mtime_ns``, the
inflated ``length``, the CSV ``header``, the ``body`` offset where the rows start and
the ``marks`` ([offset, ticker], in file order) -- and the rest is indexed_gzip's index,
zlib packed. Invalidated when the day file's size or modified time differ (a day
downloaded again): it is then not read, and the next import of that day builds it
again. An unknown ``schema_version`` or a damaged file is never read either: it is
logged and rebuilt from the day file, which is the truth. Losing every index only costs
the slow first reads again.

Without indexed_gzip installed (a desk whose packages predate it) nothing here is used:
the files stream through zlib as before, and the log says so once.
"""
from __future__ import annotations

import bisect
import importlib
import importlib.util
import io
import json
import logging
import os
import threading
import time
import zlib
from dataclasses import dataclass
from pathlib import Path

from constants_sim import (
    SIM_MASSIVE_INDEX_CHECK_SEC, SIM_MASSIVE_INDEX_LOCK_STALE_SEC, SIM_MASSIVE_INDEX_LOCK_TOUCH_SEC,
    SIM_MASSIVE_INDEX_READBUF,
    SIM_MASSIVE_INDEX_SCHEMA_VERSION, SIM_MASSIVE_INDEX_SPACING, SIM_MASSIVE_INDEX_SUBDIR, SIM_MASSIVE_INDEX_WINDOW,
    SIM_MASSIVE_READ_CHUNK, SIM_MASSIVE_STORE_SUBDIR,
)

try:
    import indexed_gzip
except ImportError:          # a desk whose packages predate it: zlib, no index (massive_files)
    indexed_gzip = None

logger = logging.getLogger(__name__)
_FORMAT = "indexed_gzip"
_PACKED = "zlib"


@dataclass(frozen=True)
class Saved:
    """A day file's saved index: the seek points, the inflated length, the map, the header and where rows start."""
    seek_points: bytes
    length: int
    marks: list[tuple[int, bytes]]
    header: list[str]
    body: int


def available() -> bool:
    return indexed_gzip is not None


_installed = {"at": float("-inf"), "found": False}
_installed_lock = threading.Lock()
NOT_INSTALLED = "indexed_gzip is not installed in the engine's Python"


def installed() -> bool:
    """Whether an import's own process would load indexed_gzip. True when this one did; otherwise looked for on
    disk (at most every SIM_MASSIVE_INDEX_CHECK_SEC), because a package installed while the API runs is used by
    the next import with no restart, and this process's import at its start would go on saying it is missing."""
    if indexed_gzip is not None:
        return True
    now = time.monotonic()
    with _installed_lock:
        if now - _installed["at"] < SIM_MASSIVE_INDEX_CHECK_SEC:
            return _installed["found"]
        importlib.invalidate_caches()
        _installed.update(at=now, found=importlib.util.find_spec("indexed_gzip") is not None)
        return _installed["found"]


def status() -> dict:
    """The replay listing's ``massive.seek_index``: can an import read a day file through its index (and build one)."""
    ok = installed()
    return dict(available=ok, reason=None if ok else NOT_INSTALLED)


def reset_status_for_tests() -> None:
    with _installed_lock:
        _installed.update(at=float("-inf"), found=False)


def path_for(day_file: Path, root: Path) -> Path:
    """Where ``day_file``'s index lives: its path under the root, beneath ``<root>/sim/index``."""
    try:
        rel = day_file.relative_to(root)
    except ValueError:      # a file outside the root (a moved folder): keyed by <dataset>/YYYY/MM/<file>
        rel = Path(*day_file.parts[-4:])
    return root / SIM_MASSIVE_STORE_SUBDIR / SIM_MASSIVE_INDEX_SUBDIR / rel.parent / f"{rel.name}.idx"


def _source(day_file: Path) -> tuple[int, int]:
    st = day_file.stat()
    return st.st_size, st.st_mtime_ns


def _marks(raw: list, length: int) -> list[tuple[int, bytes]]:
    """The saved map, checked: offsets rising within the file, tickers in the file's order."""
    marks = [(int(offset), str(ticker).encode("latin-1")) for offset, ticker in raw]
    for (a, ta), (b, tb) in zip(marks, marks[1:], strict=False):     # each mark with the one after it
        if not (a < b and ta <= tb):
            raise ValueError(f"the map is out of order at offset {b}")
    if marks and not 0 <= marks[0][0] <= marks[-1][0] <= length:
        raise ValueError("the map runs past the file")
    return marks


def load(day_file: Path, root: Path) -> Saved | None:
    """``day_file``'s index when a current one is on disk, else ``None`` (the file is then streamed from the start)."""
    where = path_for(day_file, root)
    try:
        raw = where.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as exc:
        logger.warning("Massive index %s cannot be read (%s); the day file is streamed", where, exc)
        return None
    nl = raw.find(b"\n")
    try:
        head = json.loads(raw[:nl])
        version = head.get("schema_version")
        if version != SIM_MASSIVE_INDEX_SCHEMA_VERSION:
            logger.warning("Massive index %s has schema_version %r, not %d; it is rebuilt from the day file",
                           where, version, SIM_MASSIVE_INDEX_SCHEMA_VERSION)
            return None
        if (head["size"], head["mtime_ns"]) != _source(day_file):
            logger.info("Massive index %s is for an older copy of %s; it is rebuilt", where, day_file.name)
            return None
        length, header, body = int(head["length"]), head["header"], int(head["body"])
        if not (header and all(isinstance(name, str) for name in header) and 0 < body <= length):
            raise ValueError("no header or rows")
        return Saved(zlib.decompress(raw[nl + 1:]), length, _marks(head["marks"], length), list(header), body)
    except (ValueError, KeyError, TypeError, AttributeError, zlib.error, OSError) as exc:
        logger.warning("Massive index %s is damaged (%s); it is rebuilt from the day file", where, exc)
        return None


def _save(day_file: Path, root: Path, seek_points: bytes, length: int, marks: list[tuple[int, bytes]],
          header: list[str], body: int) -> Path | None:
    """Write ``day_file``'s index (whole or not at all); a failure is logged, never the import's."""
    where = path_for(day_file, root)
    part = where.with_name(f"{where.name}.{os.getpid()}.part")
    try:
        size, mtime_ns = _source(day_file)
        head = dict(schema_version=SIM_MASSIVE_INDEX_SCHEMA_VERSION, size=size, mtime_ns=mtime_ns, length=length,
                    format=_FORMAT, packed=_PACKED, built=round(time.time(), 3), header=header, body=body,
                    marks=[[offset, ticker.decode("latin-1")] for offset, ticker in marks])
        part.write_bytes(json.dumps(head, separators=(",", ":")).encode() + b"\n" + zlib.compress(seek_points, 6))
        os.replace(part, where)
        return where
    except OSError as exc:
        logger.warning("Massive index for %s could not be written (%s); the next import builds it", day_file, exc)
        try:
            part.unlink(missing_ok=True)
        except OSError:
            logger.warning("Massive index: could not remove %s", part)
        return None


def _open(day_file: Path):
    return indexed_gzip.IndexedGzipFile(str(day_file), spacing=SIM_MASSIVE_INDEX_SPACING,
                                        window_size=SIM_MASSIVE_INDEX_WINDOW, readbuf_size=SIM_MASSIVE_INDEX_READBUF,
                                        buffer_size=SIM_MASSIVE_INDEX_READBUF, drop_handles=False)


def open_file(day_file: Path, seek_points: bytes):
    """The day file through indexed_gzip, entering it at the saved seek points."""
    handle = _open(day_file)
    try:
        handle.import_index(fileobj=io.BytesIO(seek_points))
    except BaseException:
        handle.close()
        raise
    return handle


def locate(marks: list[tuple[int, bytes]], ticker: bytes, body: int, length: int) -> tuple[int, int]:
    """``(start, end)`` in the inflated file: streaming from ``start`` (a line start) meets ``ticker``'s block, which
    is over by ``end`` (for progress). Found in the map, so it costs no read at all."""
    keys = [mark[1] for mark in marks]
    first = bisect.bisect_left(keys, ticker)        # the first mark at the ticker or past it
    start = marks[first - 1][0] if first > 0 else body
    after = bisect.bisect_right(keys, ticker)       # the first mark past it
    return start, (marks[after][0] if after < len(marks) else length)


class _Lock:
    """One build per day file across processes: ``<index>.lock``, created exclusively and rewritten while the build
    runs; one left alone for ``SIM_MASSIVE_INDEX_LOCK_STALE_SEC`` belongs to a build that died and is taken over."""

    def __init__(self, where: Path):
        self.path = where.with_name(f"{where.name}.lock")
        self.held = False
        self.touched = 0.0

    def __enter__(self) -> _Lock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    age = time.time() - self.path.stat().st_mtime
                except FileNotFoundError:
                    continue                        # released meanwhile: try again
                if age <= SIM_MASSIVE_INDEX_LOCK_STALE_SEC:
                    return self                     # another build holds it
                logger.warning("Massive index: taking over %s, untouched for %.0f s", self.path, age)
                self.path.unlink(missing_ok=True)
                continue
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            self.held, self.touched = True, time.monotonic()
            return self
        return self

    def touch(self) -> None:
        if self.held and time.monotonic() - self.touched >= SIM_MASSIVE_INDEX_LOCK_TOUCH_SEC:
            os.utime(self.path)
            self.touched = time.monotonic()

    def __exit__(self, *exc) -> None:
        if self.held:
            self.path.unlink(missing_ok=True)


def build(day_file: Path, root: Path, stop: threading.Event | None = None) -> Path | None:
    """Read ``day_file`` start to end and save its index; ``None`` when stopped, already being built, or not saved."""
    if indexed_gzip is None:
        return None
    with _Lock(path_for(day_file, root)) as lock:
        if not lock.held:
            return None
        handle = _open(day_file)
        try:
            buf = bytearray(max(int(SIM_MASSIVE_READ_CHUNK), 1))
            head = bytearray()
            header: list[str] | None = None
            body = at = 0
            marks: list[tuple[int, bytes]] = []
            while n := handle.readinto(buf):
                if stop is not None and stop.is_set():
                    return None
                lock.touch()
                lo = 0
                if header is None:                      # the first line is the header, however small the reads
                    nl = buf.find(b"\n", 0, n)
                    head += buf[:nl if nl >= 0 else n]
                    if nl < 0:
                        at += n
                        continue
                    header, body, lo = bytes(head).decode("utf-8").strip().split(","), at + nl + 1, nl
                nl = buf.find(b"\n", lo, n)             # the first line that starts in this stretch: the map's mark
                comma = buf.find(b",", nl + 1, n) if nl >= 0 else -1
                if comma > nl >= 0:
                    marks.append((at + nl + 1, bytes(buf[nl + 1:comma])))
                at += n
            if header is None:
                return None
            out = io.BytesIO()
            handle.export_index(fileobj=out)
            return _save(day_file, root, out.getvalue(), at, marks, header, body)
        finally:
            handle.close()
