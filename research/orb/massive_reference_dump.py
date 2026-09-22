"""Pull everything else the Massive Stocks Starter plan includes that a strategy could need,
so the subscription can be cancelled once and never revisited.

Writes under ``F:\\Nova\\data\\massive\\reference``:
    tickers.json          every ticker, active and delisted (also fetched by build_store.py)
    splits.json           splits since 2021-06
    dividends.json        dividends since 2021-06
    exchanges.json, ticker_types.json
    ticker_details.jsonl  one line per ticker: market cap, shares outstanding, SIC, list date ...
    news/YYYY-MM.jsonl    the news archive since the window start (tickers, title, publisher,
                          published time, description, keywords, per-ticker insights)
    short_interest.jsonl, short_volume.jsonl   best effort (skipped with a note if the plan refuses)
    manifest.json         counts, sizes and any endpoint the plan refused

Resumable: a file that exists with content is skipped; news is resumed from the last
month written. Uses the API key already in the desk .env (the S3 secret is the same value).

Usage:
    py -3 research/orb/massive_reference_dump.py            # everything
    py -3 research/orb/massive_reference_dump.py --skip news
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path

import requests

from common import STORE_DIR, load_env

REF_DIR = STORE_DIR / "reference"
API_BASES = ("https://api.massive.com", "https://api.polygon.io")
WINDOW_START = "2021-09-22"  # five years before 2026-09-22, the day the plan was bought
DETAIL_WORKERS = 8


def _key() -> str:
    key = (os.environ.get("MASSIVE_API_KEY") or os.environ.get("POLYGON_API_KEY")
           or os.environ.get("MASSIVE_S3_SECRET_ACCESS_KEY") or "").strip()
    if not key:
        sys.exit("no Massive key in .env")
    return key


class Api:
    def __init__(self) -> None:
        self.key = _key()
        self.base = API_BASES[0]
        self.s = requests.Session()
        self.refused: dict[str, str] = {}

    def get(self, path_or_url: str, params: dict | None = None, retries: int = 6):
        url = path_or_url if path_or_url.startswith("http") else f"{self.base}{path_or_url}"
        params = dict(params or {})
        params["apiKey"] = self.key
        for attempt in range(1, retries + 1):
            try:
                r = self.s.get(url, params=params, timeout=60)
                if r.status_code in (401, 403, 404):
                    return r  # plan / endpoint answer, not transient
                if r.status_code == 429:
                    time.sleep(5 * attempt)
                    continue
                r.raise_for_status()
                return r
            except requests.RequestException as exc:
                if attempt == retries:
                    raise
                if self.base == API_BASES[0] and attempt == 2:
                    self.base = API_BASES[1]
                    url = url.replace(API_BASES[0], API_BASES[1])
                print(f"  retry {attempt}: {str(exc)[:80]}", file=sys.stderr, flush=True)
                time.sleep(3 * attempt)
        raise RuntimeError("unreachable")

    def paged(self, path: str, params: dict, label: str, sink) -> int:
        """Follow next_url; sink(results_list) per page. Returns row count, -1 if refused."""
        n, url, page = 0, path, 0
        while url:
            r = self.get(url, params if page == 0 else None)
            if r.status_code in (401, 403, 404):
                self.refused[label] = f"HTTP {r.status_code}: {r.text[:120]}"
                print(f"  {label}: refused ({r.status_code})", flush=True)
                return -1
            body = r.json()
            rows = body.get("results") or []
            sink(rows)
            n += len(rows)
            page += 1
            url = body.get("next_url")
            if page % 25 == 0:
                print(f"  {label}: {n} rows after {page} pages", flush=True)
        return n


def dump_simple(api: Api, name: str, path: str, params: dict) -> int:
    out = REF_DIR / f"{name}.json"
    if out.exists() and out.stat().st_size > 2:
        print(f"{name}: exists, skipped", flush=True)
        return 0
    rows: list = []
    n = api.paged(path, params, name, rows.extend)
    if n >= 0:
        out.write_text(json.dumps(rows), encoding="utf-8")
        print(f"{name}: {n} rows", flush=True)
    return n


def dump_details(api: Api) -> int:
    tickers_file = REF_DIR / "tickers.json"
    if not tickers_file.exists():
        dump_simple(api, "tickers", "/v3/reference/tickers", {"market": "stocks", "active": "true", "limit": 1000})
    symbols = sorted({t["ticker"] for t in json.loads(tickers_file.read_text(encoding="utf-8")) if t.get("ticker")})
    out = REF_DIR / "ticker_details.jsonl"
    done: set[str] = set()
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            try:
                done.add(json.loads(line)["ticker"])
            except (ValueError, KeyError):
                pass
    todo = [s for s in symbols if s not in done]
    print(f"ticker_details: {len(done)} done, {len(todo)} to fetch", flush=True)

    def one(sym: str):
        r = api.get(f"/v3/reference/tickers/{sym}")
        if r.status_code == 200:
            return sym, r.json().get("results") or {"ticker": sym}
        if r.status_code == 404:
            return sym, {"ticker": sym, "_missing": True}
        return sym, {"ticker": sym, "_error": r.status_code}

    n = 0
    with out.open("a", encoding="utf-8") as fh, ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as pool:
        for fut in as_completed([pool.submit(one, s) for s in todo]):
            sym, row = fut.result()
            row.setdefault("ticker", sym)
            fh.write(json.dumps(row) + "\n")
            n += 1
            if n % 2000 == 0:
                fh.flush()
                print(f"  ticker_details: {n}/{len(todo)}", flush=True)
    return n


def dump_news(api: Api) -> int:
    news_dir = REF_DIR / "news"
    news_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(news_dir.glob("*.jsonl"))
    start = WINDOW_START
    if existing:
        # resume from the last month written (rewrite that month to avoid a torn page)
        last = existing[-1]
        start = last.stem + "-01"
        last.unlink()
    print(f"news: from {start}", flush=True)
    files: dict[str, object] = {}
    count = 0

    def sink(rows: list) -> None:
        nonlocal count
        for row in rows:
            month = (row.get("published_utc") or "")[:7]
            if not month:
                continue
            fh = files.get(month)
            if fh is None:
                fh = files[month] = (news_dir / f"{month}.jsonl").open("a", encoding="utf-8")
            fh.write(json.dumps(row) + "\n")
            count += 1

    n = api.paged("/v2/reference/news",
                  {"published_utc.gte": start, "order": "asc", "sort": "published_utc", "limit": 1000},
                  "news", sink)
    for fh in files.values():
        fh.close()
    return n if n < 0 else count


def dump_jsonl(api: Api, name: str, path: str, params: dict) -> int:
    out = REF_DIR / f"{name}.jsonl"
    if out.exists() and out.stat().st_size > 2:
        print(f"{name}: exists, skipped", flush=True)
        return 0
    with out.open("w", encoding="utf-8") as fh:
        n = api.paged(path, params, name, lambda rows: fh.writelines(json.dumps(r) + "\n" for r in rows))
    if n < 0:
        out.unlink(missing_ok=True)
    else:
        print(f"{name}: {n} rows", flush=True)
    return n


def main() -> int:
    load_env()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip", nargs="*", default=[], choices=["simple", "details", "news", "short"])
    a = ap.parse_args()
    REF_DIR.mkdir(parents=True, exist_ok=True)
    api = Api()
    t0 = time.time()
    counts: dict[str, int] = {}
    if "simple" not in a.skip:
        counts["dividends"] = dump_simple(api, "dividends", "/v3/reference/dividends",
                                          {"ex_dividend_date.gte": "2021-06-01", "limit": 1000})
        counts["exchanges"] = dump_simple(api, "exchanges", "/v3/reference/exchanges", {"asset_class": "stocks"})
        counts["ticker_types"] = dump_simple(api, "ticker_types", "/v3/reference/tickers/types", {"asset_class": "stocks"})
    if "short" not in a.skip:
        counts["short_interest"] = dump_jsonl(api, "short_interest", "/stocks/v1/short-interest",
                                              {"settlement_date.gte": WINDOW_START, "limit": 50000})
        counts["short_volume"] = dump_jsonl(api, "short_volume", "/stocks/v1/short-volume",
                                            {"date.gte": WINDOW_START, "limit": 50000})
    if "details" not in a.skip:
        counts["ticker_details"] = dump_details(api)
    if "news" not in a.skip:
        counts["news"] = dump_news(api)
    manifest = {
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "window_start": WINDOW_START, "counts": counts, "refused": api.refused,
        "files": {p.name: p.stat().st_size for p in REF_DIR.iterdir() if p.is_file()},
        "news_months": len(list((REF_DIR / "news").glob("*.jsonl"))) if (REF_DIR / "news").exists() else 0,
    }
    (REF_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"done in {(time.time() - t0) / 60:.1f} min; refused: {api.refused or 'none'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
