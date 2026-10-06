"""Confirm the splits Massive's list misses from SEC filings, for the leaderboard rebuild (#772).

A rebuilt day adjusts its prior close (and RVOL lookback) only for the splits it knows; a missed
reverse split reads as a giant overnight mover (PHGE on 2026-09-09: +925%). This tool finds the
overnight jumps no listed split explains, reads the ticker's split filings, and writes the splits
a filing proves to ``splits_confirmed.json`` beside the leaderboard store, where
``lb_io.load_splits`` reads them back. The rules are ``split_confirm.py``'s and AGENTS.md
section 3's ("Splits a rebuild confirms from SEC filings").

Usage (from the repo root):
    py -3 research/leaderboard/confirm_splits.py --start 2026-06-16 --end 2026-09-21
    py -3 research/leaderboard/confirm_splits.py --start 2026-06-16 --end 2026-09-21 --dry-run

It prints the rebuilt days each confirmed split changes, for
``build_leaderboard.py --dates``. SEC is asked for each filing's documents once; their text is
kept by accession under ``split_filings`` beside the store.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import sys
import zipfile
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lb_config import (  # noqa: E402
    CONFIRMED_SPLITS_PATH,
    CONFIRMED_SPLITS_SCHEMA_VERSION,
    DATA_ROOT,
    DAY_SUBDIR,
    MINUTE_SUBDIR,
    REFERENCE_SUBDIR,
    RESEARCH_DB,
    RVOL_LOOKBACK_SESSIONS,
    SPLIT_6K_FORMS,
    SPLIT_8K_FORMS,
    SPLIT_8K_ITEMS,
    SPLIT_FILING_CACHE_DIR,
    SPLIT_FILING_CACHE_SUFFIX,
    SPLIT_FILING_DAYS_AFTER,
    SPLIT_FILING_DAYS_BEFORE,
    SPLIT_LISTED_NEARBY_SESSIONS,
    SPLIT_MAX_EXHIBITS,
    SPLIT_SUSPECT_DOWN,
    SPLIT_SUSPECT_UP,
)
import lb_io  # noqa: E402
import split_confirm  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "catalysts"))
import fetch_edgar  # noqa: E402  (the bulk submissions reader and the CIK map, research/catalysts)
from cat_config import SEC_CALLS_PER_SEC, load_env, sec_user_agent  # noqa: E402
from http_util import HttpRefused, Pacer, get  # noqa: E402

from catalysts.sec_text import EXHIBIT_RE, text_of  # noqa: E402  (backend: one reader for SEC documents)

ET = ZoneInfo("America/New_York")


# ── Inputs ──────────────────────────────────────────────────────────────────

def read_day_aggs(path: Path) -> dict[str, tuple[float, float, float]]:
    """One day_aggs file: ticker -> (open, close, volume)."""
    out: dict[str, tuple[float, float, float]] = {}
    with gzip.open(path, "rt", newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                out[row["ticker"]] = (float(row["open"]), float(row["close"]), float(row["volume"]))
            except (KeyError, TypeError, ValueError):
                continue   # a row without a price is no evidence either way
    return out


def _filed(ts: float) -> date:
    return datetime.fromtimestamp(ts, ET).date()


class Filings:
    """A company's 8-K / 6-K list: SEC's bulk file on F:, else (past its date) SEC's live JSON."""

    def __init__(self, zip_path: Path, ua: dict, pacer: Pacer):
        self.zip = zipfile.ZipFile(zip_path)
        self.zip_date = datetime.fromtimestamp(zip_path.stat().st_mtime, ET).date()
        self.ua, self.pacer = ua, pacer
        self._cache: dict[tuple[str, bool], list[dict]] = {}

    def for_company(self, cik: str, through: date) -> list[dict]:
        live = through > self.zip_date
        key = (cik, live)
        if key not in self._cache:
            self._cache[key] = self._live(cik) if live else [
                {"acc": f["acc"], "form": f["form"], "items": f["items"] or "", "doc": f["doc"], "filed": _filed(f["ts"])}
                for f in fetch_edgar.filings(self.zip, cik)
            ]
        return self._cache[key]

    def _live(self, cik: str) -> list[dict]:
        sub = get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json", self.ua, self.pacer)
        recent = sub.get("filings", {}).get("recent", {})
        col = lambda key, i: (recent.get(key) or [""] * (i + 1))[i] or ""  # noqa: E731
        return [
            {"acc": acc, "form": col("form", i), "items": col("items", i), "doc": col("primaryDocument", i),
             "filed": date.fromisoformat(col("filingDate", i))}
            for i, acc in enumerate(recent.get("accessionNumber", [])) if col("filingDate", i)
        ]


def split_filings(filings: Sequence[dict], session: date) -> list[dict]:
    """The filings that could state a split taking effect on ``session``, nearest first."""
    lo, hi = session - timedelta(days=SPLIT_FILING_DAYS_BEFORE), session + timedelta(days=SPLIT_FILING_DAYS_AFTER)
    out = [
        f for f in filings
        if lo <= f["filed"] <= hi and (
            (f["form"] in SPLIT_8K_FORMS and any(item in f["items"] for item in SPLIT_8K_ITEMS))
            or f["form"] in SPLIT_6K_FORMS)
    ]
    return sorted(out, key=lambda f: abs((f["filed"] - session).days))


def filing_text(cik: str, filing: dict, ua: dict, pacer: Pacer) -> str:
    """The filing's primary document, then its EX-99 exhibits when that states no ratio; kept by accession."""
    cache = SPLIT_FILING_CACHE_DIR / f"{filing['acc']}{SPLIT_FILING_CACHE_SUFFIX}"
    if cache.is_file():
        return cache.read_text(encoding="utf-8")
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{filing['acc'].replace('-', '')}"
    parts = []
    if filing["doc"]:
        parts.append(" ".join(text_of(get(f"{base}/{filing['doc']}", ua, pacer, as_json=False))))
    if not any(split_confirm.mentions(p) for p in parts):
        listing = get(f"{base}/index.json", ua, pacer)
        names = [item["name"] for item in listing.get("directory", {}).get("item", [])]
        exhibits = [n for n in names if EXHIBIT_RE.search(n) and n.lower().endswith((".htm", ".html", ".txt"))]
        for name in exhibits[:SPLIT_MAX_EXHIBITS]:
            parts.append(" ".join(text_of(get(f"{base}/{name}", ua, pacer, as_json=False))))
    text = "\n".join(parts)
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(cache.suffix + ".part")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, cache)
    return text


# ── One suspect ─────────────────────────────────────────────────────────────

def decide(suspect: split_confirm.Suspect, texts: Sequence[tuple[dict, str]]) -> tuple[dict | None, dict | None]:
    """(confirmed split, refusal) for one suspect from its filings' texts; both None when no filing names a split."""
    verdicts = [(f, split_confirm.judge(text, prev_session=suspect.prev_session, session=suspect.session,
                                        prev_close=suspect.prev_close, open_=suspect.open)) for f, text in texts]
    confirmed = [(f, v) for f, v in verdicts if v.confirmed]
    if confirmed:
        ratios = {(v.split_from, v.split_to) for _f, v in confirmed}
        if len(ratios) > 1:
            stated = ", ".join(f"{a}/{b}" for a, b in sorted(ratios))
            return None, _refusal(suspect, confirmed[0][0], f"filings state different ratios: {stated}")
        f, v = sorted(confirmed, key=lambda fv: fv[1].date_match is not True)[0]
        return {
            "ticker": suspect.ticker, "execution_date": suspect.session.isoformat(),
            "split_from": v.split_from, "split_to": v.split_to,
            "cik": None, "form": f["form"], "items": f["items"], "accession": f["acc"], "filed": f["filed"].isoformat(),
            "url": None, "ratio_text": v.ratio_text, "date_match": v.date_match,
            "prev_session": suspect.prev_session.isoformat(), "prev_close": suspect.prev_close, "open": suspect.open,
            "price_ratio": suspect.price_ratio, "adjusted_ratio": v.adjusted_ratio, "volume_ratio": suspect.volume_ratio,
        }, None
    named = [(f, v) for f, v in verdicts if v.names_split]
    if named:
        f, v = named[0]
        return None, _refusal(suspect, f, v.reason)
    return None, None


def _refusal(suspect: split_confirm.Suspect, filing: dict | None, reason: str) -> dict:
    return {"ticker": suspect.ticker, "execution_date": suspect.session.isoformat(),
            "accession": filing["acc"] if filing else None, "reason": reason}


# ── The file ────────────────────────────────────────────────────────────────

def read_confirmed(path: Path) -> dict:
    """The confirmed-splits file, or an empty one; an unknown version refuses."""
    if not path.is_file():
        return {"schema_version": CONFIRMED_SPLITS_SCHEMA_VERSION, "updated_at": None, "spans": [], "splits": [], "refused": []}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != CONFIRMED_SPLITS_SCHEMA_VERSION:
        raise SystemExit(f"{path}: schema_version {raw.get('schema_version')!r} is not "
                         f"{CONFIRMED_SPLITS_SCHEMA_VERSION}; refusing to overwrite it")
    return raw


def merge(existing: Mapping, *, start: date, end: date, span: dict, splits: list[dict], refused: list[dict],
          now: datetime) -> dict:
    """``existing`` with this span's entries replaced by this run's; every other span's kept."""
    def outside(entry: Mapping) -> bool:
        return not (start <= date.fromisoformat(entry["execution_date"]) <= end)

    return {
        "schema_version": CONFIRMED_SPLITS_SCHEMA_VERSION,
        "updated_at": now.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "spans": sorted([s for s in existing.get("spans", []) if (s["start"], s["end"]) != (start.isoformat(), end.isoformat())]
                        + [span], key=lambda s: (s["start"], s["end"])),
        "splits": sorted([s for s in existing.get("splits", []) if outside(s)] + splits,
                         key=lambda s: (s["execution_date"], s["ticker"])),
        "refused": sorted([r for r in existing.get("refused", []) if outside(r)] + refused,
                          key=lambda r: (r["execution_date"], r["ticker"])),
    }


def write_confirmed(path: Path, data: Mapping) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


# ── The run ─────────────────────────────────────────────────────────────────

def _rebuilt_days() -> set[str]:
    """Days the store already holds rebuilt (read-only: a day not yet built takes the split when it is)."""
    from leaderboard import store   # backend on sys.path via cat_config / lb_config

    db = store.read_only()
    if db is None:
        return set()
    try:
        return {row[0] for row in db.execute(
            "SELECT DISTINCT session_date FROM coverage WHERE source = 'reconstructed'").fetchall()}
    finally:
        db.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", required=True, help="first session, YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="last session, YYYY-MM-DD")
    ap.add_argument("--out", type=Path, default=CONFIRMED_SPLITS_PATH, help="the confirmed-splits file")
    ap.add_argument("--dry-run", action="store_true", help="judge and print, write no file")
    args = ap.parse_args()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    load_env()
    ua, pacer = {"User-Agent": sec_user_agent()}, Pacer(SEC_CALLS_PER_SEC)

    research, note = lb_io.open_research_db(RESEARCH_DB)
    print(note, flush=True)
    try:
        reference = lb_io.load_reference(research, DATA_ROOT / REFERENCE_SUBDIR)
        massive = lb_io.load_splits(research, DATA_ROOT / REFERENCE_SUBDIR, confirmed=None)   # Massive's own list
    finally:
        if research is not None:
            research.close()
    listed: dict[str, list[date]] = {}
    for s in massive:
        listed.setdefault(s.ticker, []).append(s.execution_date)

    calendar = list(lb_io.files_by_date(DATA_ROOT / MINUTE_SUBDIR))
    day_files = lb_io.files_by_date(DATA_ROOT / DAY_SUBDIR)
    span = [d for d in calendar if start <= d <= end]
    if not span:
        raise SystemExit("no sessions in that range")
    first = calendar.index(span[0])
    aggs = {d: read_day_aggs(day_files[d]) for d in calendar[max(0, first - 1):calendar.index(span[-1]) + 1 + RVOL_LOOKBACK_SESSIONS]
            if d in day_files}
    universe = reference.universe()

    found: list[split_confirm.Suspect] = []
    for d in span:
        i = calendar.index(d)
        prev = calendar[i - 1] if i else None
        if prev is None or prev not in aggs or d not in aggs:
            continue
        found += split_confirm.suspects(aggs[prev], aggs[d], prev_session=prev, session=d, universe=universe,
                                        listed=listed, up=SPLIT_SUSPECT_UP, down=SPLIT_SUSPECT_DOWN)
    print(f"{len(found)} suspects in {span[0]}..{span[-1]} (open >= {SPLIT_SUSPECT_UP}x or <= {SPLIT_SUSPECT_DOWN}x "
          f"the prior close, no split listed)", flush=True)

    ciks = fetch_edgar.cik_map()
    filings = Filings(fetch_edgar.ZIP, ua, pacer)
    splits, refused, with_filings, unread = [], [], 0, 0
    for n, suspect in enumerate(found, 1):
        i = calendar.index(suspect.session)
        window = calendar[max(0, i - SPLIT_LISTED_NEARBY_SESSIONS):i + SPLIT_LISTED_NEARBY_SESSIONS + 1]
        nearby = [d for d in listed.get(suspect.ticker, ()) if window[0] <= d <= window[-1]]
        cik = ciks.get(suspect.ticker)
        if not cik:
            continue
        try:
            candidates = split_filings(filings.for_company(cik, suspect.session + timedelta(days=SPLIT_FILING_DAYS_AFTER)),
                                       suspect.session)
        except (HttpRefused, OSError, ValueError, KeyError) as exc:
            unread += 1
            refused.append(_refusal(suspect, None, f"could not read the filing list: {exc}"))
            continue
        if not candidates:
            continue
        with_filings += 1
        texts = []
        for f in candidates:
            try:
                texts.append((f, filing_text(cik, f, ua, pacer)))
            except (HttpRefused, OSError, ValueError, KeyError) as exc:
                unread += 1
                refused.append(_refusal(suspect, f, f"could not read the filing: {exc}"))
        split, refusal = decide(suspect, texts)
        if split is not None and nearby:
            listed_on = ", ".join(d.isoformat() for d in nearby)
            refusal = _refusal(suspect, None, f"Massive lists a split for {suspect.ticker} on {listed_on}: not added twice")
            split = None
        if split is not None:
            split["cik"] = cik
            split["url"] = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{split['accession'].replace('-', '')}/"
            splits.append(split)
            print(f"  confirmed {suspect.ticker} {suspect.session}: {split['split_from']}/{split['split_to']} "
                  f"({split['form']} {split['accession']}, filed {split['filed']}; adjusted open "
                  f"{split['adjusted_ratio']}x the prior close; date match {split['date_match']})", flush=True)
        elif refusal is not None:
            refused.append(refusal)
        if n % 50 == 0:
            print(f"  {n}/{len(found)} suspects looked at", flush=True)

    now = datetime.now(timezone.utc)
    span_row = {"start": start.isoformat(), "end": end.isoformat(), "checked_at": now.isoformat(timespec="seconds"),
                "suspects": len(found), "with_filings": with_filings, "confirmed": len(splits), "refused": len(refused)}
    print(f"{len(splits)} confirmed, {len(refused)} refused, {with_filings} suspects had a split-type filing, "
          f"{unread} reads failed", flush=True)
    for r in refused:
        print(f"  refused {r['ticker']} {r['execution_date']}: {r['reason']}", flush=True)
    if not args.dry_run:
        write_confirmed(args.out, merge(read_confirmed(args.out), start=start, end=end, span=span_row,
                                        splits=splits, refused=refused, now=now))
        print(f"wrote {args.out}", flush=True)

    rebuilt = _rebuilt_days()
    days: set[date] = set()
    for s in splits:
        traded = {d for d, rows in aggs.items() if s["ticker"] in rows}
        days.update(split_confirm.affected_sessions(date.fromisoformat(s["execution_date"]), calendar, traded,
                                                    RVOL_LOOKBACK_SESSIONS))
    todo = sorted(d.isoformat() for d in days if d.isoformat() in rebuilt)
    if todo:
        print("rebuild the days these splits change:", flush=True)
        print(f"  py -3 research/leaderboard/build_leaderboard.py --dates {','.join(todo)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
