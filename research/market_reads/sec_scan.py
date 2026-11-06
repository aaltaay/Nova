"""Who filed a form, across every listed company, in a span of days (ADR 059): SEC's ``submissions.zip`` read company
by company -- "every 424B5 filed 2026-09-08 .. 09-14", "S-1s of SIC 2834 companies in March 2021".

The zip (``<NOVA_CATALYST_DIR>/edgar/submissions.zip``, through ``sec.py``'s one handle, read-only) holds one JSON
per SEC registrant -- 985,826 of them, 4.9 GB inflated -- and no index by form or day. A scan reads the companies in
Massive's ticker list (``symbols.by_cik``: 13,957 CIKs, active and delisted, every company that held a ticker Massive
lists); a filer that never did (a fund, a trust, a private issuer, a company that never listed) is not scanned unless
``ciks`` names it. Measured 2026-10-26 on the 2026-09-22 zip, every listed company (inflating their 1.2 GB of JSON
is the floor, ~5 s): 424B5 over a week 6.6 s (56 rows), 8-K over a week 8.7 s (920), the broadest month 17-18 s
(Form 4 over August 2026: 12,037 rows; 8-K over May 2018, older pages read: 7,088), S-1 / 424B4 of SIC 2834 over a
month 1.9 s. A process's first SEC read adds ~10 s (the zip's directory, 6.6 s, and Massive's lists). Hence a span of
at most ``MAX_SPAN_DAYS``; ``tickers`` / ``ciks`` / ``sic`` narrow the read.

A company's JSON is parsed only when its bytes hold a form asked for, quoted (``"424B5"``), and a month of the span
(``"2026-09-``); an older page (``CIK...-submissions-001.json``) is read only when its ``filingFrom`` .. ``filingTo``
overlaps the span. Forms match exactly as SEC writes them (asked in any case): ``S-1`` is not ``S-1/A`` -- name both.

Rows: one per filing per company whose SEC record lists it (a Schedule 13D/G or a Form 4 is listed under the subject
company as well as the filer: each row says its own cik). ``ticker`` is the ticker the company held on the filing
day: a listing row not delisted before it, listed by then when Massive's ticker details give a ``list_date``, a
reused ticker only on a day ``tickers.resolve`` names this company, common stock first (None: it held none Massive
knows of that day -- a filing before its listing, or after its last delisting). ``tickers`` lists every ticker Massive
gives the CIK, as written (``AAp`` is not ``AAP``). ``sic`` is SEC's own code in the filer's record, today's.
Acceptance time: SEC writes every ``acceptanceDateTime`` with a ``Z`` though some filers' JSON holds Eastern wall
time; each is placed by ``research/catalysts/edgar_clock.py`` (the catalyst backfill's rule, loaded from its file,
never forked) over the filer's whole JSON (``edgar_clock.placed``: a part's votes are counted only when a row needs
them -- 4,517 scanned rows placed exactly as ``clocks`` places them on the real zip); ``accepted_clock`` says what
placed it.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from datetime import date, timedelta
from typing import Any

import pandas as pd

from market_reads import REPO, roots, sec, slots, symbols, tickers

MAX_SPAN_DAYS = 31
ZIP = "submissions.zip"
COLUMNS = ["filed", "accepted_et", "form", "ticker", "tickers", "cik", "company", "sic", "accession", "report_date",
           "items", "accepted_clock"]
RULE = ("a filing counts from its filing date; accepted_et is SEC's acceptance time placed on its own clock "
        "(research/catalysts/edgar_clock.py)")
COVERAGE = ("companies in Massive's ticker list (active and delisted) unless ciks names others; every EDGAR filing "
            "they list, the zip's whole history")
_SIC = re.compile(rb'"sic"\s*:\s*"(\d*)"')
_FILES = b'"files"'
_HEAD_BYTES = 1024


def _clock():
    """``research/catalysts/edgar_clock.py`` under its own module name: the backfill's clock rule, read, never forked.
    Loaded when this module is (the MCP server imports readers on its main thread before stdio starts)."""
    name = "market_reads_edgar_clock"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, REPO / "research" / "catalysts" / "edgar_clock.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


_clock()


def _span(date_from: str, date_to: str) -> tuple[str, str]:
    lo, hi = date.fromisoformat(str(date_from)), date.fromisoformat(str(date_to))
    if hi < lo:
        raise ValueError(f"date_to {hi} is before date_from {lo}")
    if (hi - lo).days + 1 > MAX_SPAN_DAYS:
        raise ValueError(f"a filings scan spans at most {MAX_SPAN_DAYS} days ({lo} .. {hi} is {(hi - lo).days + 1}): "
                         "every listed company's SEC record is read per call, so split the span")
    return lo.isoformat(), hi.isoformat()


def _months(lo: str, hi: str) -> list[bytes]:
    """``"YYYY-MM-`` for each month the span touches: a JSON with no date in them has no filing in the span."""
    out, month, end = [], date.fromisoformat(lo).replace(day=1), date.fromisoformat(hi)
    while month <= end:
        out.append(f'"{month:%Y-%m}-'.encode())
        month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
    return out


def sic_matches(code: str | None, wanted: list[str]) -> bool:
    """``code`` is one of ``wanted``: ``2834`` exactly, ``283*`` any code starting 283 (codes read as 4 digits)."""
    if not code or not str(code).strip().isdigit():
        return False
    padded = str(code).strip().zfill(4)
    return any(padded.startswith(w[:-1]) if w.endswith("*") else padded == w for w in wanted)


def sic_codes(sic: list[str] | str | int | None) -> list[str]:
    """The asked SIC codes as 4-digit strings (``"283*"`` kept as a prefix); [] when none."""
    items = [sic] if isinstance(sic, (str, int)) else list(sic or [])
    out = []
    for item in (str(i).strip() for i in items if str(i).strip()):
        digits = item[:-1] if item.endswith("*") else item
        if not digits.isdigit() or len(digits) > 4 or (not item.endswith("*") and not digits):
            raise ValueError(f"sic {item!r}: a 4-digit SIC code (2834) or a prefix ending * (283*)")
        out.append(f"{digits}*" if item.endswith("*") else digits.zfill(4))
    return out


def _read(member: str, limit: int | None = None) -> bytes | None:
    archive = sec._zip(ZIP)
    with sec._LOCK:                     # one ZipFile shares one file handle: reads must not interleave
        try:
            if limit is None:
                return archive.read(member)
            with archive.open(member) as fh:
                return fh.read(limit)
        except KeyError:
            return None


def _pages(raw: bytes) -> list[dict[str, Any]]:
    """The ``filings.files`` list (older pages) from a company's JSON bytes, without parsing the rest."""
    at = raw.rfind(_FILES)                 # the last key of the record: nothing after it can hold the word
    start = raw.find(b"[", at) if at >= 0 else -1
    if start < 0:
        return []
    pages, _ = json.JSONDecoder().raw_decode(raw[start:].decode("utf-8"))
    return pages if isinstance(pages, list) else []


def _at(block: dict, key: str, i: int):
    column = block.get(key) or ()
    return column[i] if i < len(column) else None


def _hits(block: dict, wanted: set[str], lo: str, hi: str) -> list[int]:
    """Rows of one part with a form asked for (as SEC writes it, upper case) filed inside the span."""
    n = len(block.get("accessionNumber") or [])
    dates = block.get("filingDate") or []
    return [i for i, form in enumerate((block.get("form") or [])[:n])
            if form in wanted and i < len(dates) and lo <= str(dates[i] or "") <= hi]


def _rows_of(block: dict) -> list[tuple[str, str, str | None]]:
    """A part's ``(form, raw acceptance, filing date)`` rows, one per accession, as the backfill builds them."""
    n = len(block.get("accessionNumber") or [])

    def column(key: str, fill):
        values = list(block.get(key) or [])[:n]
        return [v or fill for v in values] + [fill] * (n - len(values))

    return list(zip(column("form", ""), column("acceptanceDateTime", ""), column("filingDate", None), strict=True))


def _pool(ticker_list: list[str] | None, ciks: list[str] | None, lo: str, hi: str) -> tuple[list[str], list[str]]:
    """The CIKs to read and the warnings naming them: every listed company, else the asked ones (a ticker names the
    company that held it on ``lo`` and on ``hi``; a day ``tickers.resolve`` cannot settle refuses -- pass ``ciks``)."""
    if not ticker_list and not ciks:
        return sorted(symbols.by_cik()), []
    pool, warnings = {tickers._cik(c) for c in ciks or []} - {None}, []
    for symbol in ticker_list or []:
        for day in (lo, hi):
            held = tickers.require(symbol, day)
            pool.add(held["cik"])
            if held["warning"] and held["warning"] not in warnings:
                warnings.append(held["warning"])
    return sorted(pool), warnings


class _Names:
    """Each company's tickers for one scan: Massive's list read once, every answer kept."""

    def __init__(self):
        self.listed, self.by_cik, self.list_dates = tickers.listings(), symbols.by_cik(), _list_dates()
        self._on: dict[tuple[str, str], str | None] = {}
        self._every: dict[str, str] = {}

    def on(self, cik: str, day: str) -> str | None:
        """The ticker ``cik`` held on ``day`` (the module docstring's rule), common stock first; None when none."""
        if (cik, day) not in self._on:
            held = []
            for row in self.by_cik.get(cik, []):
                symbol = str(row.get("ticker") or "").strip()
                gone = str(row.get("delisted_utc") or "")[:10]
                if not symbol or (gone and gone < day) or (self.list_dates.get(symbol) or "") > day:
                    continue
                if len({tickers._cik(r.get("cik")) for r in self.listed.get(symbol, [])}) > 1 and \
                        tickers.resolve(symbol, day)["cik"] != cik:
                    continue
                held.append((row.get("type") not in tickers.COMMON_TYPES, not row.get("active"), len(symbol), symbol))
            self._on[(cik, day)] = min(held)[3] if held else None
        return self._on[(cik, day)]

    def every(self, cik: str) -> str:
        """Every ticker Massive gives ``cik``, as written: common stock first, then active before delisted."""
        if cik not in self._every:
            ranked = sorted({(r.get("type") not in tickers.COMMON_TYPES, not r.get("active"), str(r.get("ticker")))
                             for r in self.by_cik.get(cik, []) if r.get("ticker")})
            self._every[cik] = ",".join(dict.fromkeys(t for *_, t in ranked))
        return self._every[cik]


def _list_dates() -> dict[str, str]:
    """Ticker (as written) -> Massive ticker details' ``list_date``; {} when the dump has no ticker details."""
    from market_reads import reference
    try:
        frame = reference.ticker_details_all()
    except LookupError:  # maintainer: allow-swallow no ticker details leaves every listing window open-ended
        return {}
    if frame.empty or "list_date" not in frame:
        return {}
    known = frame[frame["list_date"].notna()]
    return dict(zip(known["ticker"].astype(str), known["list_date"].astype(str).str[:10], strict=True))


def _company_rows(cik: str, doc: dict, pages: dict[str, dict], found: list[tuple[str | None, int]],
                  names: _Names) -> list[dict[str, Any]]:
    """Each hit as a row. Its acceptance time is placed by the backfill's rule over the filer's whole JSON, built only
    as far as the rule needs: the parts holding hits, the rest only when a hit falls to the filer's majority."""
    clock = _clock()
    recent = (doc.get("filings") or {}).get("recent") or {}
    blocks: dict[str | None, dict] = {None: recent, **pages}
    keys = list(dict.fromkeys(name for name, _ in found))
    index = {name: k for k, name in enumerate(keys)}

    def others() -> list[list[tuple[str, str, str | None]]]:
        rest = [] if None in index else [_rows_of(recent)]
        for page in (doc.get("filings") or {}).get("files") or []:
            name = page.get("name", "")
            block = None if name in index else json.loads(_read(name) or b"null")
            if block is not None:          # a page the zip lacks is skipped, as the backfill skips it
                rest.append(_rows_of(block))
        return rest

    marks = clock.placed([_rows_of(blocks[k]) for k in keys], [(index[name], i) for name, i in found], others)
    out = []
    for (name, i), (placed, how) in zip(found, marks, strict=True):
        block = blocks[name]
        raw, filed = _at(block, "acceptanceDateTime", i) or "", _at(block, "filingDate", i)
        out.append({"filed": filed, "accepted_ts": clock.accepted_ts(raw, placed) if placed else None,
                    "form": _at(block, "form", i), "ticker": names.on(cik, filed), "tickers": names.every(cik),
                    "cik": cik, "company": doc.get("name"), "sic": doc.get("sic") or None,
                    "accession": _at(block, "accessionNumber", i), "report_date": _at(block, "reportDate", i) or None,
                    "items": _at(block, "items", i) or None, "accepted_clock": how or None})
    return out


def filings_scan(forms: list[str] | str, date_from: str, date_to: str, ticker_list: list[str] | None = None,
                 ciks: list[str] | None = None, sic: list[str] | str | None = None) -> pd.DataFrame:
    """Every filing of ``forms`` filed ``date_from`` .. ``date_to`` (at most ``MAX_SPAN_DAYS``) by the listed
    companies, or only ``ticker_list`` / ``ciks``, or only companies whose SEC SIC is in ``sic``: ``COLUMNS``, by
    filing date, then acceptance time (one accepted after 17:30 ET is dated the next business day)."""
    wanted = {str(f).strip().upper() for f in ([forms] if isinstance(forms, str) else forms or []) if str(f).strip()}
    if not wanted:
        raise ValueError("forms is required, e.g. ['424B5'] or ['S-1', 'S-1/A']")
    lo, hi = _span(date_from, date_to)
    codes = sic_codes(sic)
    pool, warnings = _pool(ticker_list, ciks, lo, hi)
    needles, months = [f'"{f}"'.encode() for f in wanted], _months(lo, hi)
    counts = {"companies": len(pool), "no_sec_record": 0, "other_sic": 0, "parsed": 0, "pages_read": 0}
    rows: list[dict[str, Any]] = []
    names = _Names()                    # before the slot: a stale ticker-details index takes one to rebuild
    with slots.heavy(f"sec filings scan {lo}..{hi}"):
        for cik in pool:
            member = f"CIK{cik.zfill(10)}.json"
            if codes:
                head = _read(member, _HEAD_BYTES) or b""
                code = _SIC.search(head)
                if not sic_matches(code.group(1).decode() if code else None, codes):
                    counts["other_sic" if head else "no_sec_record"] += 1
                    continue
            raw = _read(member)
            if raw is None:
                counts["no_sec_record"] += 1
                continue
            doc, found, pages = None, [], {}
            if any(n in raw for n in needles) and any(m in raw for m in months):
                doc = json.loads(raw)
                counts["parsed"] += 1
                found = [(None, i) for i in _hits((doc.get("filings") or {}).get("recent") or {}, wanted, lo, hi)]
            for page in ((doc.get("filings") or {}).get("files") if doc else _pages(raw)) or []:
                if (page.get("filingFrom") or "") <= hi and (page.get("filingTo") or "9999") >= lo:
                    page_raw = _read(page.get("name", ""))
                    counts["pages_read"] += 1
                    if page_raw and any(n in page_raw for n in needles):
                        pages[page["name"]] = block = json.loads(page_raw)
                        found += [(page["name"], i) for i in _hits(block, wanted, lo, hi)]
            if found:
                rows += _company_rows(cik, doc if doc is not None else json.loads(raw), pages, found, names)
    frame = pd.DataFrame(rows, columns=[*COLUMNS[:1], "accepted_ts", *COLUMNS[2:]])
    frame.insert(1, "accepted_et", pd.to_datetime(frame["accepted_ts"], unit="s", utc=True).dt.tz_convert(
        "America/New_York"))
    frame = frame.drop(columns="accepted_ts").sort_values(["filed", "accepted_et", "cik", "accession"],
                                                          na_position="last").reset_index(drop=True)
    frame.attrs.update(forms=sorted(wanted), date_from=lo, date_to=hi, tickers=ticker_list or None, ciks=ciks or None,
                       sic=codes or None, scanned=counts, rule=RULE, coverage=COVERAGE, warnings=warnings,
                       max_span_days=MAX_SPAN_DAYS, source=str(roots.edgar() / ZIP),
                       note="forms match exactly (S-1 is not S-1/A); sic is SEC's code today, not as of the day")
    return frame
