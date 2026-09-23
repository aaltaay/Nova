"""SEC EDGAR filings for every target: the bulk submissions index on F:, press releases fetched.

  1. ticker -> CIK from the Massive reference dump on F: (delisted names included), else SEC's
     current ``company_tickers.json`` (cached beside the zip)
  2. each company's filings from ``edgar/submissions.zip`` (SEC's nightly bulk file, kept on F:)
  3. filings accepted inside a target's window (``acceptanceDateTime`` is UTC; checked against
     the filing index page's Eastern "Accepted" time)
  4. for an 8-K / 6-K, the press release itself: the EX-99 exhibit (else the primary document),
     reduced to its headline and opening text -- the release the company legally filed, so it can
     never be a movers list or a law-firm advert

Resumable: answered targets are skipped; fetched exhibits are kept as items and never re-read.

Usage:  py -3 research/catalysts/fetch_edgar.py [--limit N]
"""
from __future__ import annotations

import argparse
import json
import zipfile
from collections import defaultdict
from datetime import datetime

from cat_config import EDGAR_DIR, REFERENCE_DIR, SEC_CALLS_PER_SEC, load_env, sec_user_agent
from http_util import HttpRefused, Pacer, get
from store import connect, pending, put_check, put_items

from catalysts.sec_text import KEEP_FORMS, PRESS_FORMS, describe, release_text  # shared with the live feed

SOURCE = "edgar"
ZIP = EDGAR_DIR / "submissions.zip"
def cik_map() -> dict[str, str]:
    out: dict[str, str] = {}
    for row in json.loads((REFERENCE_DIR / "tickers.json").read_text(encoding="utf-8")):
        if row.get("cik") and row.get("ticker"):
            out.setdefault(row["ticker"].upper(), str(row["cik"]).lstrip("0"))
    cache = EDGAR_DIR / "company_tickers.json"
    if not cache.exists():
        cache.write_text(json.dumps(get("https://www.sec.gov/files/company_tickers.json",
                                        {"User-Agent": sec_user_agent()}, Pacer(SEC_CALLS_PER_SEC))), encoding="utf-8")
    for v in json.loads(cache.read_text(encoding="utf-8")).values():
        out.setdefault(str(v["ticker"]).upper(), str(v["cik_str"]))
    return out


def filings(z: zipfile.ZipFile, cik: str) -> list[dict]:
    """Every filing SEC lists for a company: the recent block plus its older pages."""
    name = f"CIK{cik.zfill(10)}.json"
    try:
        sub = json.loads(z.read(name))
    except KeyError:
        return []
    blocks = [sub.get("filings", {}).get("recent", {})]
    for f in sub.get("filings", {}).get("files", []):
        try:
            blocks.append(json.loads(z.read(f["name"])))
        except KeyError:
            continue
    out = []
    for b in blocks:
        for i, acc in enumerate(b.get("accessionNumber", [])):
            t = b["acceptanceDateTime"][i]
            if not t:
                continue
            out.append({"acc": acc, "form": b["form"][i], "items": b.get("items", [""] * (i + 1))[i] or "",
                        "doc": b.get("primaryDocument", [""] * (i + 1))[i] or "",
                        "ts": datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp()})
    return out


def press_release(cik: str, f: dict, ua: dict, pacer: Pacer) -> tuple[str | None, str]:
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{f['acc'].replace('-', '')}"
    listing = get(f"{base}/index.json", ua, pacer)
    names = [it["name"] for it in listing.get("directory", {}).get("item", [])]
    return release_text(f["form"], names, f["doc"], lambda doc: get(f"{base}/{doc}", ua, pacer, as_json=False))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    load_env()
    if not ZIP.exists():
        raise SystemExit(f"{ZIP} missing -- download SEC's bulk submissions.zip there first")
    ua = {"User-Agent": sec_user_agent()}
    pacer = Pacer(SEC_CALLS_PER_SEC)
    ciks = cik_map()
    con = connect()
    todo = pending(con, SOURCE)[: a.limit or None]
    by_ticker: dict[str, list[tuple]] = defaultdict(list)
    for row in todo:
        by_ticker[row[0]].append(row)
    z = zipfile.ZipFile(ZIP)
    fetched = {r[0] for r in con.execute("SELECT item_id FROM items WHERE source = 'edgar'")}
    n_items = 0
    for i, (ticker, rows) in enumerate(sorted(by_ticker.items()), 1):
        cik = ciks.get(ticker)
        if not cik:
            with con:
                for t in rows:
                    put_check(con, ticker, t[1], SOURCE, "unavailable", detail="no CIK for this ticker")
            continue
        fl = filings(z, cik)
        for _t, day, w0, _cut, w1 in rows:
            items, err = [], None
            for f in fl:
                if not (w0 < f["ts"] <= w1) or f["form"] not in KEEP_FORMS:
                    continue
                item_id = f"edgar:{f['acc']}"
                title, summary = describe(f["form"], f["items"]), ""
                if f["form"] in PRESS_FORMS and item_id not in fetched:
                    try:
                        head, summary = press_release(cik, f, ua, pacer)
                        title = f"{describe(f['form'], f['items'])} | {head}" if head else title
                    except HttpRefused as e:
                        summary = f"(exhibit unavailable: {e})"
                    except Exception as e:  # noqa: BLE001 -- the target is retried next run
                        err = str(e)[:200]
                        break
                items.append({"item_id": item_id, "source": SOURCE, "published_ts": f["ts"], "title": title,
                              "summary": summary[:2000], "publisher": "SEC EDGAR", "form": f["form"],
                              "sec_items": f["items"], "tickers": [ticker], "n_tickers": 1,
                              "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{f['acc'].replace('-', '')}/"})
            with con:
                if err:
                    put_check(con, ticker, day, SOURCE, "error", detail=err)
                    continue
                put_items(con, items)
                put_check(con, ticker, day, SOURCE, "ok", n_items=len(items))
            fetched.update(it["item_id"] for it in items)
            n_items += len(items)
        if i % 200 == 0:
            print(f"  {i}/{len(by_ticker)} tickers, {n_items} filings", flush=True)
    print(f"edgar: {len(todo)} symbol-days, {n_items} filings", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
