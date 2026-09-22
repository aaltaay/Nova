"""Download Massive (formerly Polygon) US-stocks flat files to the F: drive.

Pulls every daily ``minute_aggs_v1`` and ``day_aggs_v1`` file for the
subscribed range into ``F:\\Nova\\data\\massive\\<dataset>\\YYYY\\MM\\YYYY-MM-DD.csv.gz``.
Resumable: a file whose size matches the bucket listing is skipped.

Credentials come from the desk ``.env`` (never from this file):
    MASSIVE_S3_ACCESS_KEY_ID=...
    MASSIVE_S3_SECRET_ACCESS_KEY=...
Optional:
    MASSIVE_S3_ENDPOINT=https://files.massive.com   (files.polygon.io also works)
    NOVA_MARKET_DATA_DIR=F:\\Nova\\data\\massive

Usage:
    py -3 massive_flatfiles.py --check                # credentials + bucket reachable
    py -3 massive_flatfiles.py --list 2024-01          # what the bucket holds that month
    py -3 massive_flatfiles.py --from 2021-09-01       # download minute + day aggs to today
    py -3 massive_flatfiles.py --from 2021-09-01 --dataset day_aggs_v1
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path

RETRIES = 8
RETRY_SLEEP_SEC = 3
WORKERS = 4  # whole files in parallel (not multipart ranges); one stalled link no longer blocks the rest
DEFAULT_ENDPOINT = "https://files.massive.com"
FALLBACK_ENDPOINT = "https://files.polygon.io"
BUCKET = "flatfiles"
PREFIX = "us_stocks_sip"
DATASETS = ("minute_aggs_v1", "day_aggs_v1")
DEFAULT_DIR = Path(r"F:\Nova\data\massive")


def _load_env() -> None:
    """Read the repo-root .env without overriding real environment variables."""
    for candidate in (Path(__file__).resolve().parent, Path.cwd(), *Path.cwd().parents):
        env = candidate / ".env"
        if env.is_file():
            for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
            return


def _client(endpoint: str):
    import boto3
    from botocore.config import Config

    key = os.environ.get("MASSIVE_S3_ACCESS_KEY_ID") or os.environ.get("POLYGON_S3_ACCESS_KEY_ID")
    secret = os.environ.get("MASSIVE_S3_SECRET_ACCESS_KEY") or os.environ.get("POLYGON_S3_SECRET_ACCESS_KEY")
    if not key or not secret:
        sys.exit(
            "Missing MASSIVE_S3_ACCESS_KEY_ID / MASSIVE_S3_SECRET_ACCESS_KEY in .env "
            "(Dashboard > Flat Files > S3 credentials). The REST API key is a different value."
        )
    session = boto3.Session(aws_access_key_id=key, aws_secret_access_key=secret)
    cfg = Config(
        signature_version="s3v4",
        retries={"max_attempts": 10, "mode": "adaptive"},
        connect_timeout=15,
        read_timeout=20,  # a stalled transfer on this link sits for minutes; cut it and retry
    )
    return session.client("s3", endpoint_url=endpoint, config=cfg)


def _transfer_config():
    """One stream per file: parallel range requests trip TLS record errors on this link."""
    from boto3.s3.transfer import TransferConfig

    return TransferConfig(use_threads=False, multipart_threshold=1024 ** 3)


def _listing(s3, dataset: str, year: int, month: int) -> dict[str, int]:
    prefix = f"{PREFIX}/{dataset}/{year:04d}/{month:02d}/"
    out: dict[str, int] = {}
    token = None
    while True:
        kwargs = {"Bucket": BUCKET, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kwargs)
        for obj in resp.get("Contents", []):
            out[obj["Key"]] = int(obj["Size"])
        if not resp.get("IsTruncated"):
            return out
        token = resp.get("NextContinuationToken")


def _months(start: date, end: date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


def _fetch_one(s3, key: str, dest: Path, size: int) -> int:
    """Download one object to dest with retries; returns bytes written."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(f".{os.getpid()}.{threading.get_ident()}.part")
    for attempt in range(1, RETRIES + 1):
        try:
            s3.download_file(BUCKET, key, str(tmp), Config=_transfer_config())
            if tmp.stat().st_size != size:
                raise RuntimeError(f"size mismatch: got {tmp.stat().st_size}, listed {size}")
            tmp.replace(dest)
            return size
        except Exception as exc:  # noqa: BLE001 - stalls and TLS record errors are the norm on this link
            tmp.unlink(missing_ok=True)
            if "403" in str(exc) or "Forbidden" in str(exc):
                print(f"forbidden (outside the plan's window?) {key}", file=sys.stderr, flush=True)
                return 0
            if attempt == RETRIES:
                raise
            print(f"retry {attempt}/{RETRIES} {key}: {str(exc)[:90]}", file=sys.stderr, flush=True)
            time.sleep(RETRY_SLEEP_SEC * attempt)
    return 0


def download(s3, dataset: str, start: date, end: date, root: Path) -> tuple[int, int, int]:
    got = skipped = bytes_total = 0
    for y, m in _months(start, end):
        listing = _listing(s3, dataset, y, m)
        jobs: list[tuple[str, Path, int, str]] = []
        for key in sorted(listing):
            day = key.rsplit("/", 1)[-1].removesuffix(".csv.gz")
            try:
                d = date.fromisoformat(day)
            except ValueError:
                continue
            if d < start or d > end:
                continue
            dest = root / dataset / f"{y:04d}" / f"{m:02d}" / f"{day}.csv.gz"
            size = listing[key]
            if dest.is_file() and dest.stat().st_size == size:
                skipped += 1
                continue
            jobs.append((key, dest, size, day))
        if not jobs:
            continue
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = {pool.submit(_fetch_one, s3, key, dest, size): day for key, dest, size, day in jobs}
            for fut in as_completed(futures):
                n = fut.result()  # raises on a file that failed every retry -> runner restarts us
                got += 1
                bytes_total += n
                print(f"{dataset} {futures[fut]} {n / 1e6:7.1f} MB", flush=True)
    return got, skipped, bytes_total


def main() -> int:
    _load_env()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="verify credentials and bucket access, then exit")
    ap.add_argument("--list", metavar="YYYY-MM", help="list one month of a dataset and exit")
    ap.add_argument("--from", dest="start", metavar="YYYY-MM-DD", help="first day to download")
    ap.add_argument("--to", dest="end", metavar="YYYY-MM-DD", default=None, help="last day (default: yesterday)")
    ap.add_argument("--dataset", choices=DATASETS + ("all",), default="all")
    ap.add_argument("--dir", default=os.environ.get("NOVA_MARKET_DATA_DIR") or str(DEFAULT_DIR))
    ap.add_argument("--endpoint", default=os.environ.get("MASSIVE_S3_ENDPOINT") or DEFAULT_ENDPOINT)
    args = ap.parse_args()

    root = Path(args.dir)
    try:
        s3 = _client(args.endpoint)
        s3.head_bucket(Bucket=BUCKET)
    except Exception as exc:  # noqa: BLE001 - report and try the legacy host once
        if args.endpoint == DEFAULT_ENDPOINT:
            print(f"{DEFAULT_ENDPOINT} refused ({exc}); trying {FALLBACK_ENDPOINT}", file=sys.stderr)
            s3 = _client(FALLBACK_ENDPOINT)
            s3.head_bucket(Bucket=BUCKET)
        else:
            raise

    if args.check:
        sample = _listing(s3, "day_aggs_v1", date.today().year, 1)
        print(f"ok: bucket reachable, {len(sample)} day files listed for January {date.today().year}")
        print(f"data dir: {root}")
        return 0

    if args.list:
        y, m = (int(p) for p in args.list.split("-"))
        for ds in DATASETS if args.dataset == "all" else (args.dataset,):
            listing = _listing(s3, ds, y, m)
            total = sum(listing.values())
            print(f"{ds} {args.list}: {len(listing)} files, {total / 1e9:.2f} GB")
        return 0

    if not args.start:
        ap.error("--from YYYY-MM-DD is required to download (or use --check / --list)")
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end) if args.end else date.today() - timedelta(days=1)
    root.mkdir(parents=True, exist_ok=True)
    for ds in DATASETS if args.dataset == "all" else (args.dataset,):
        got, skipped, nbytes = download(s3, ds, start, end, root)
        print(f"{ds}: downloaded {got}, already had {skipped}, {nbytes / 1e9:.2f} GB new")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
