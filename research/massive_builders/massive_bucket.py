"""Massive's flat-file bucket and the raw files on disk: the S3 client, the month listing, the ranged resumable
download, the gzip integrity check and its record (``verified.jsonl``), the cached file list (``plan_cache.json``)
and the archive window (whole calendar years from 2016, newest first).

Raw layout, as Massive serves it: ``<NOVA_MARKET_DATA_DIR>/<dataset>/YYYY/MM/YYYY-MM-DD.csv.gz`` with ``.part``
while a file is arriving. A day counts as downloaded only when the file's size equals the size Massive lists.
"""
from __future__ import annotations

import json
import os
import sys
import time
import zlib
from datetime import date, datetime
from pathlib import Path

from massive_env import NY, ROOT, env_values
from massive_jobs import log, parent_gone

BUCKET = "flatfiles"
PREFIX = "us_stocks_sip"
CHUNK = 32 * 2**20
RESUME_BACKOFF = 2 * CHUNK               # a resumed download starts this far before the end of its .part (see fetch)
VERIFIED = ROOT / "verified.jsonl"       # one line per file read whole through gzip: {f, size, ok, why, at}
VERIFY_HALT = ROOT / "verify_halted.txt" # written when a verify run finds more than 3 bad files: the check stops until someone removes it
WINDOW_START = date(2016, 1, 1)          # phase 1 of the operator's plan: the last ten years, as whole calendar years
PLAN_CACHE = ROOT / "plan_cache.json"    # {"built": epoch, "plan": {dataset: {YYYY-MM-DD: size}}}: Massive's own file list, kept by the supervisor


def year_periods() -> list[tuple[str, date, date, bool]]:
    """(name, first day, last day, newest first?): one period per calendar year, newest year first. The name is the year."""
    today = date.today()
    return [(str(y), max(date(y, 1, 1), WINDOW_START), min(date(y, 12, 31), today), True) for y in range(today.year, WINDOW_START.year - 1, -1)]


def client(max_attempts: int = 4, mode: str = "standard"):
    """boto3 S3 client on Massive's endpoint with the MASSIVE_S3_* pair (env or .env; never printed)."""
    import boto3
    from botocore.config import Config
    vals = env_values()
    key, secret = vals.get("MASSIVE_S3_ACCESS_KEY_ID"), vals.get("MASSIVE_S3_SECRET_ACCESS_KEY")
    if not key or not secret:
        sys.exit("no MASSIVE_S3_* pair in the environment or the .env (NOVA_ENV_PATH)")
    return boto3.Session(aws_access_key_id=key, aws_secret_access_key=secret).client(
        "s3", endpoint_url=vals.get("MASSIVE_S3_ENDPOINT") or "https://files.massive.com",
        config=Config(signature_version="s3v4", retries={"max_attempts": max_attempts, "mode": mode}, connect_timeout=15, read_timeout=30))


def listing(s3, dataset: str, y: int, m: int) -> dict[str, int]:
    out = {}; token = None
    while True:
        kw = {"Bucket": BUCKET, "Prefix": f"{PREFIX}/{dataset}/{y:04d}/{m:02d}/"}
        if token:
            kw["ContinuationToken"] = token
        r = s3.list_objects_v2(**kw)
        for o in r.get("Contents", []):
            out[o["Key"]] = int(o["Size"])
        if not r.get("IsTruncated"):
            return out
        token = r.get("NextContinuationToken")


def months(a: date, b: date):
    y, m = a.year, a.month
    while (y, m) <= (b.year, b.month):
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


def sub(d: date, ext: str) -> Path:
    """YYYY/MM/YYYY-MM-DD<ext>: the per-day layout of every raw file and product."""
    return Path(f"{d.year:04d}") / f"{d.month:02d}" / f"{d.isoformat()}{ext}"


def verify_gzip(path: Path) -> tuple[bool, str]:
    """Read a whole file through gzip and say whether it is intact. A truncated file, a zero-filled tail or a damaged block fails:
    gzip checks its own CRC and length at the end of every member. Nothing is kept; it reads about 80 MB/s of the file on one core."""
    d = zlib.decompressobj(31)
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(8 * 2**20), b""):
                while chunk:
                    if d.eof:                           # the next member of a multi-member file
                        d = zlib.decompressobj(31)
                    d.decompress(chunk)
                    chunk = d.unused_data if d.eof else b""
    except zlib.error as exc:
        return False, f"damaged: {str(exc)[:80]}"
    except OSError as exc:
        return False, f"unreadable: {str(exc)[:80]}"
    return (True, "") if d.eof else (False, "the file ends before its gzip stream does")


def rel_of(p: Path) -> str:
    try:
        return p.relative_to(ROOT).as_posix()
    except ValueError:
        return p.as_posix()


def record_verified(path: Path, size: int, ok: bool, why: str = "") -> None:
    with open(VERIFIED, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"f": rel_of(path), "size": size, "ok": ok, "why": why, "at": datetime.now(NY).isoformat(timespec="seconds")}) + "\n")


def load_verified() -> dict[str, tuple[int, bool]]:
    """{relative path: (size, ok)} of the last record of every file; a line that cannot be read is skipped."""
    out: dict[str, tuple[int, bool]] = {}
    try:
        for line in VERIFIED.read_text(encoding="utf-8").splitlines():
            try:
                j = json.loads(line); out[j["f"]] = (int(j["size"]), bool(j["ok"]))
            except (ValueError, KeyError, TypeError):
                continue
    except OSError:
        pass
    return out


def check_new_file(path: Path, size: int) -> bool:
    """Right after a download: read the file through gzip, note it, and throw it away if it is damaged (it is fetched again)."""
    ok, why = verify_gzip(path)
    record_verified(path, size, ok, why)
    if not ok:
        log(f"DAMAGED {rel_of(path)}: {why}; deleted, it is fetched again")
        path.unlink(missing_ok=True)
    return ok


def fetch(s3, key: str, dest: Path, size: int) -> float:
    """Ranged, resumable download of the file exactly as Massive serves it. Returns seconds spent.
    Raises PermissionError when the server keeps answering 403: on 2026-10-05 it answered 403 to a burst of requests and
    read the same files a minute later, so a 403 is asked again a few times before the day is given up on."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    have = part.stat().st_size if part.exists() else 0
    if have > size:
        part.unlink(); have = 0
    if have:                                    # a power cut can leave the last seconds of a file as zeros under a correct length, so resume a little earlier
        have = max(have - RESUME_BACKOFF, 0)
        with open(part, "r+b") as fh:
            fh.truncate(have)
    t0 = time.time(); fails = 0; denied = 0
    try:
        with open(part, "ab") as fh:
            while have < size:
                if parent_gone():
                    raise SystemExit("the process that started this worker is gone")
                end = min(have + CHUNK, size) - 1
                try:
                    r = s3.get_object(Bucket=BUCKET, Key=key, Range=f"bytes={have}-{end}")
                    buf = r["Body"].read()
                    if len(buf) != end - have + 1:
                        raise OSError(f"short read {len(buf)} of {end - have + 1}")
                    fh.write(buf); fh.flush(); os.fsync(fh.fileno())     # on the disk before the next chunk: what the file says it holds, it holds
                    have += len(buf); fails = 0; denied = 0
                except Exception as exc:  # noqa: BLE001 - TLS record errors and stalls are normal on this link
                    if "403" in str(exc) or "Forbidden" in str(exc):
                        denied += 1
                        if denied > 3:
                            raise PermissionError(key) from exc
                        time.sleep(5 * denied)
                        continue
                    fails += 1
                    if fails > 12:
                        raise
                    time.sleep(min(60, 2 * fails))
                    try:
                        s3 = client()
                    except Exception:  # noqa: BLE001
                        pass
    except PermissionError:
        if part.exists() and part.stat().st_size == 0:
            part.unlink()                                   # a refused day leaves no empty file behind
        raise
    part.replace(dest)
    return time.time() - t0


def cached_days(dataset: str, a: date, b: date) -> dict[date, tuple[str, int]] | None:
    """The days of a dataset from the supervisor's copy of Massive's file list (plan_cache.json), None when there is no
    fresh copy. It saves a listing of every month each time a job starts."""
    try:
        c = json.loads(PLAN_CACHE.read_text(encoding="utf-8"))
        if time.time() - float(c["built"]) > 12 * 3600:
            return None
        sizes = c["plan"][dataset]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    out = {}
    for iso, size in sizes.items():
        d = date.fromisoformat(iso)
        if a <= d <= b:
            out[d] = (f"{PREFIX}/{dataset}/{d.year:04d}/{d.month:02d}/{iso}.csv.gz", int(size))
    return out


def dataset_days(s3, dataset: str, a: date, b: date) -> dict[date, tuple[str, int]]:
    """{day: (key, size)} of one dataset between a and b: the cached list when fresh, else Massive's month listings."""
    cached = cached_days(dataset, a, b)
    if cached is not None:
        return cached
    out = {}
    for y, m in months(a, b):
        for key, size in listing(s3, dataset, y, m).items():
            try:
                d = date.fromisoformat(key.rsplit("/", 1)[-1].removesuffix(".csv.gz"))
            except ValueError:
                continue
            if a <= d <= b:
                out[d] = (key, size)
    return out
