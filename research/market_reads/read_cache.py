"""The front door's read cache: one stock-day of a Massive dataset, parsed once, kept as an Arrow IPC file.

A read of a symbol's slice of a day file inflates gzip and parses CSV in Python (seconds to a minute for a busy name);
the same read out of the cache is one Arrow file load. ``reads.read_file`` asks here first and fills the entry on a
miss; the frame it returns is the same either way (columns, dtypes, values, row order, ``attrs``).

Owner: this module is the only reader and writer of ``<root>/<dataset>/<YYYY-MM-DD>/t_<SYMBOL>.arrow``. The entry holds
the whole day's rows for the symbol as parsed, before any time window or added column.
Invalidation: an entry is used only while the day file's path, size and modification time (ns) and the reader's
fingerprint (``SCHEMA_VERSION``, the code that finds and parses the rows, pandas and pyarrow versions) match what it
was written with; anything else is a miss that is read again and overwritten. ``schema_version`` lives in the file's
Arrow metadata; another version is a miss (logged once), never a guess. Contract: "Read cache" in
architecture/schema/agent-desk.md.

Switches: ``NOVA_MARKET_READ_CACHE=0`` (or ``off``) turns it off; ``NOVA_MARKET_READ_CACHE_DIR`` moves it (default
``F:\\Nova\\market_read_cache`` when F: is mounted on Windows, else off); ``NOVA_MARKET_READ_CACHE_GB`` caps it (default
50; the oldest-used entries go first); no entry is written while the drive has less than ``RESERVE_GB`` free.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import logging
import os
import re
import secrets
import threading
from collections.abc import Callable
from pathlib import Path

import pandas as pd
import pyarrow as pa

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
SWITCH_ENV = "NOVA_MARKET_READ_CACHE"
DIR_ENV = "NOVA_MARKET_READ_CACHE_DIR"
CAP_ENV = "NOVA_MARKET_READ_CACHE_GB"
DEFAULT_ROOT_WIN = r"F:\Nova\market_read_cache"
DEFAULT_CAP_GB = 50.0
RESERVE_GB = 50.0                      # never fill the data drive the recordings also live on
PRUNE_EVERY_BYTES = 1 << 30            # look at the folder's total again after this much is written
PRUNE_TO = 0.9                         # a prune stops at 90% of the cap
SUFFIX = ".arrow"
META_KEY = b"nova_read_cache"
OFF = {"0", "off", "false", "no"}
COMPRESSION = "zstd"                   # half the size of lz4 here, and as quick to read back
_SAFE = re.compile(r"[^A-Z0-9._-]")
_lock = threading.Lock()
_written_since_prune = [PRUNE_EVERY_BYTES]   # the first write of a process looks at the folder
_said_version: set = set()


def root() -> Path | None:
    """The cache folder, or ``None`` when the cache is off."""
    if (os.environ.get(SWITCH_ENV) or "").strip().lower() in OFF:
        return None
    explicit = os.environ.get(DIR_ENV)
    if explicit:
        return Path(explicit)
    if os.name == "nt" and Path(DEFAULT_ROOT_WIN[:3]).exists():
        return Path(DEFAULT_ROOT_WIN)
    return None


def cap_bytes() -> int:
    try:
        gb = float(os.environ.get(CAP_ENV) or DEFAULT_CAP_GB)
    except ValueError:
        gb = DEFAULT_CAP_GB
    return int(max(gb, 0.0) * 1e9)


def entry(base: Path, dataset: str, symbol: str, day: str) -> Path:
    """``t_`` keeps a ticker such as CON or NUL from naming a Windows device; anything outside A-Z 0-9 . _ - is
    written as ``%XX``."""
    name = _SAFE.sub(lambda m: "".join(f"%{b:02X}" for b in m.group().encode()), symbol.strip().upper())
    return base / dataset / day / f"t_{name}{SUFFIX}"


def source_identity(path: Path) -> dict:
    info = path.stat()
    return {"path": str(path), "size": info.st_size, "mtime_ns": info.st_mtime_ns}


def fingerprint(*parts: object) -> str:
    """The reader's identity: what found and parsed the rows. ``parts`` are functions (their source counts) or
    plain values; the versions of pandas and pyarrow always count."""
    digest = hashlib.sha256(f"{SCHEMA_VERSION}|{pd.__version__}|{pa.__version__}".encode())
    for part in parts:
        text = inspect.getsource(part) if callable(part) or inspect.ismodule(part) else repr(part)
        digest.update(b"\0" + text.encode())
    return digest.hexdigest()


def load(dataset: str, symbol: str, day: str, source: Path, reader: str) -> tuple[pd.DataFrame, bool] | None:
    """``(frame, indexed)`` as first read, or ``None`` on a miss (no entry, another source, another reader)."""
    base = root()
    if base is None:
        return None
    path = entry(base, dataset, symbol, day)
    try:
        with pa.OSFile(str(path), "rb") as handle:
            reader_file = pa.ipc.open_file(handle)
            meta = json.loads((reader_file.schema.metadata or {}).get(META_KEY, b"{}"))
            if not _matches(meta, dataset, symbol, day, source, reader, path):
                return None
            table = reader_file.read_all()
    except FileNotFoundError:
        return None
    except (OSError, ValueError, pa.ArrowException) as exc:     # a damaged entry is a miss and is written again
        logger.warning("read cache entry %s could not be read (%s); reading the day file", path, exc)
        return None
    if meta["rows"] == 0:
        frame = pd.DataFrame(columns=meta["header"])
    else:
        frame = table.to_pandas()
        if list(frame.columns) != meta["header"] or len(frame) != meta["rows"]:
            logger.warning("read cache entry %s does not hold what its metadata says; reading the day file", path)
            return None
    _touch(path)
    return frame, bool(meta["indexed"])


def _well_formed(meta: object) -> bool:
    """Every field ``load`` uses is there with its type; anything else (damage, a foreign writer) is a miss."""
    return (isinstance(meta, dict) and isinstance(meta.get("indexed"), bool)
            and isinstance(meta.get("header"), list) and all(isinstance(name, str) for name in meta["header"])
            and type(meta.get("rows")) is int and meta["rows"] >= 0)


def _matches(meta: object, dataset: str, symbol: str, day: str, source: Path, reader: str, path: Path) -> bool:
    version = meta.get("schema_version") if isinstance(meta, dict) else None
    if version != SCHEMA_VERSION:
        if repr(version) not in _said_version:
            _said_version.add(repr(version))
            logger.info("read cache entry %s has schema_version %r, not %d: read again", path, version, SCHEMA_VERSION)
        return False
    if not _well_formed(meta):
        logger.warning("read cache entry %s has incomplete metadata; reading the day file", path)
        return False
    try:
        current = source_identity(source)
    except OSError:
        return False
    return (meta.get("dataset") == dataset and meta.get("symbol") == symbol.strip().upper() and meta.get("day") == day
            and meta.get("source") == current and meta.get("reader") == reader)


def save(dataset: str, symbol: str, day: str, source: Path, reader: str, before: dict, frame: pd.DataFrame,
         header: list[str], indexed: bool) -> None:
    """Write the entry atomically, only when the day file did not change while it was read. A cache that cannot be
    written never fails the read (logged)."""
    base = root()
    if base is None:
        return
    try:
        if source_identity(source) != before:
            return
        target = entry(base, dataset, symbol, day)
        target.parent.mkdir(parents=True, exist_ok=True)
        if _free_bytes(target.parent) < RESERVE_GB * 1e9:
            return
        meta = {"schema_version": SCHEMA_VERSION, "dataset": dataset, "symbol": symbol.strip().upper(), "day": day,
                "source": before, "reader": reader, "indexed": bool(indexed), "header": list(header),
                "rows": int(len(frame))}
        table = pa.Table.from_pandas(frame if len(frame) else pd.DataFrame(), preserve_index=False)
        table = table.replace_schema_metadata({**(table.schema.metadata or {}), META_KEY: json.dumps(meta).encode()})
        staging = target.with_name(f".{target.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
        try:
            with pa.OSFile(str(staging), "wb") as sink, pa.ipc.new_file(
                    sink, table.schema, options=pa.ipc.IpcWriteOptions(compression=COMPRESSION)) as writer:
                writer.write_table(table)
            os.replace(staging, target)
        finally:
            staging.unlink(missing_ok=True)
        written = target.stat().st_size
    except (OSError, ValueError, pa.ArrowException) as exc:
        logger.warning("read cache could not keep %s %s %s (%s)", dataset, symbol, day, exc)
        return
    with _lock:
        _written_since_prune[0] += written
        due = _written_since_prune[0] >= PRUNE_EVERY_BYTES
        if due:
            _written_since_prune[0] = 0
    if due:
        prune(base, cap_bytes())


def _free_bytes(folder: Path) -> float:
    import shutil
    try:
        return shutil.disk_usage(folder).free
    except OSError:
        return 0.0


def _touch(path: Path) -> None:
    """A hit marks the entry used (its modified time), so the prune keeps what jobs still read."""
    try:
        os.utime(path)
    except OSError:
        pass                                   # another process holds it; the next hit marks it


def entries(base: Path) -> list[tuple[int, int, Path]]:
    """``(mtime_ns, size, path)`` of every entry under ``base``."""
    out = []
    for path in base.glob(f"*/*/t_*{SUFFIX}"):
        try:
            info = path.stat()
        except OSError:
            continue
        out.append((info.st_mtime_ns, info.st_size, path))
    return out


def prune(base: Path, cap: int, log: Callable[[str], None] | None = None) -> dict:
    """Delete the oldest-used entries until the folder holds at most 90% of ``cap`` bytes (when over ``cap``)."""
    found = sorted(entries(base))
    total = sum(size for _, size, _ in found)
    removed = freed = 0
    if total > cap:
        goal = cap * PRUNE_TO
        for _, size, path in found:
            if total - freed <= goal:
                break
            try:
                path.unlink()
            except OSError:
                continue                       # open in another process: left for the next prune
            removed, freed = removed + 1, freed + size
    answer = {"entries": len(found) - removed, "bytes": total - freed, "removed": removed, "freed": freed, "cap": cap}
    if removed and log is None:
        logger.info("read cache pruned %d entries (%.1f GB) under %s", removed, freed / 1e9, base)
    elif log is not None:
        log(json.dumps(answer))
    return answer
