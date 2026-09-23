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
import html
import json
import re
import zipfile
from collections import defaultdict
from datetime import datetime

from cat_config import EDGAR_DIR, REFERENCE_DIR, SEC_CALLS_PER_SEC, load_env, sec_user_agent
from http_util import HttpRefused, Pacer, get
from store import connect, pending, put_check, put_items

SOURCE = "edgar"
ZIP = EDGAR_DIR / "submissions.zip"
PRESS_FORMS = {"8-K", "6-K"}
KEEP_FORMS = PRESS_FORMS | {"8-K/A", "6-K/A", "424B1", "424B3", "424B4", "424B5", "S-1", "F-1", "S-3", "F-3",
                            "425", "8-A12B", "SC TO-T", "SC 14D9", "DEFM14A", "10-Q", "10-K", "20-F", "S-4", "F-4"}
ITEM_NAMES = {
    "1.01": "Material agreement", "1.02": "Agreement terminated", "1.03": "Bankruptcy", "2.01": "Acquisition completed",
    "2.02": "Results of operations", "2.03": "Financial obligation", "3.01": "Delisting notice",
    "3.02": "Unregistered equity sale", "3.03": "Rights modified", "5.01": "Change in control",
    "5.02": "Officer / director change", "5.03": "Charter / bylaws (e.g. reverse split)", "5.07": "Shareholder vote",
    "7.01": "Regulation FD", "8.01": "Other events", "9.01": "Exhibits",
}
EXHIBIT_RE = re.compile(r"(ex|exhibit|dex)[-_ ]?99", re.I)
BLOCK_RE = re.compile(r"<\s*(br|/p|/div|/tr|/h[1-6]|/li|/td)\b[^>]*>", re.I)
BOILER_RE = re.compile(r"^(ex(hibit)?[- ]?99|for immediate release|press release|news release|source:|contact|"
                       r"investor|media|nasdaq:|nyse|page \d|\(?[a-z .]+,? ?(inc|corp|ltd)\.?\)?$)|"
                       r"pursuant to|securities exchange act|report of foreign private issuer|form (6|8)-k|"
                       r"commission file|indicate by check mark|washington, d\.?c|united states securities|"
                       r"current report|date of report|incorporated by reference|forward-looking|"
                       r"for the month of|commission file number|address of principal|name of registrant|"
                       r"translation of registrant|exact name|specified in its charter", re.I)
LEAD_VERB_RE = re.compile(r"^(announces|agrees|reports|secures|receives|enters|signs|completes|launches|regains|"
                          r"closes|prices|expands|awarded|wins|partners|provides|to acquire|acquires)\b", re.I)
DATELINE_RE = re.compile(r"^[A-Z][A-Za-z .,'-]+,\s+[A-Z][a-z]+\.? \d{1,2},? \d{4}")


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


def text_of(raw: str) -> list[str]:
    raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    raw = BLOCK_RE.sub("\n", raw)
    raw = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    return [re.sub(r"\s+", " ", ln).strip() for ln in raw.splitlines() if ln.strip()]


def headline(lines: list[str]) -> tuple[str | None, str]:
    """The release's headline (first real sentence-length line) and its opening text."""
    title = None
    for k, ln in enumerate(lines[:80]):
        words = ln.split()
        if len(words) < 3 or len(words) > 45 or BOILER_RE.search(ln) or DATELINE_RE.match(ln):
            continue
        prev = lines[k - 1] if k else ""
        if LEAD_VERB_RE.match(ln) and 0 < len(prev.split()) <= 6 and not BOILER_RE.search(prev):
            ln = f"{prev} {ln}"  # the company name sat on its own line
        nxt = lines[k + 1] if k + 1 < len(lines) else ""
        if len(ln.split()) < 8 and nxt and len(nxt.split()) <= 30 and not BOILER_RE.search(nxt) and not DATELINE_RE.match(nxt):
            ln = f"{ln} {nxt}"  # the headline wrapped
        if len(ln.split()) < 5:
            continue
        title = ln
        break
    body = " ".join(lines)
    m = re.search(r"[^.]{0,200}\b(announce[sd]?|today|reported|entered into)\b.{0,1200}", body, re.I)
    return title, (m.group(0) if m else body[:1400])


def press_release(cik: str, f: dict, ua: dict, pacer: Pacer) -> tuple[str | None, str]:
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{f['acc'].replace('-', '')}"
    listing = get(f"{base}/index.json", ua, pacer)
    names = [it["name"] for it in listing.get("directory", {}).get("item", []) if it["name"].lower().endswith((".htm", ".html", ".txt"))]
    ex = sorted(n for n in names if EXHIBIT_RE.search(n))
    doc = ex[0] if ex else f["doc"]
    if not doc:
        return None, ""
    lines = text_of(get(f"{base}/{doc}", ua, pacer, as_json=False))
    if not ex and f["form"].startswith("8-K"):
        # No press release attached: the form itself. Keep what the Item says, never its cover as a headline.
        body = " ".join(lines)
        m = re.search(r"Item\s+[1-8]\.0\d.{0,1400}", body)
        return None, (m.group(0) if m else "")
    return headline(lines)


def describe(f: dict) -> str:
    codes = [c.strip() for c in f["items"].split(",") if c.strip() and c.strip() != "9.01"]
    names = "; ".join(ITEM_NAMES.get(c, c) for c in codes)
    return f"{f['form']}{': ' + names if names else ''}"


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
                title, summary = describe(f), ""
                if f["form"] in PRESS_FORMS and item_id not in fetched:
                    try:
                        head, summary = press_release(cik, f, ua, pacer)
                        title = f"{describe(f)} | {head}" if head else title
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
