"""Point-in-time shares outstanding and short interest into the research store (``orb.duckdb``).

  sec_shares      every ``dei:EntityCommonStockSharesOutstanding`` (else us-gaap
                  ``CommonStockSharesOutstanding``) a company reported, with the date it was **filed** --
                  so a backtest reads only what was public by then. From SEC's bulk ``companyfacts.zip``
                  kept on F:. Shares outstanding, not float: the float pillar's research stand-in
                  where ``ticker_details`` only knows today's count.
  short_interest  FINRA bi-monthly short interest from the Massive reference dump on F:
                  (settlement date, shares short, average daily volume, days to cover). FINRA
                  publishes about eight business days after settlement; readers lag by
                  ``SHORT_INTEREST_LAG_DAYS``.

Only the companies the catalyst targets name are read from the zip (every ticker ever a target).

Usage:  py -3 research/catalysts/build_shares.py
"""
from __future__ import annotations

import json
import zipfile
from collections import defaultdict

import duckdb

from cat_config import EDGAR_DIR, REFERENCE_DIR, RESEARCH_DB
from store import connect as catalyst_db

ZIP = EDGAR_DIR / "companyfacts.zip"
CONCEPTS = (("dei", "EntityCommonStockSharesOutstanding"), ("us-gaap", "CommonStockSharesOutstanding"))


def cik_tickers(wanted: set[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for row in json.loads((REFERENCE_DIR / "tickers.json").read_text(encoding="utf-8")):
        sym, cik = str(row.get("ticker") or "").upper(), str(row.get("cik") or "").lstrip("0")
        if sym in wanted and cik:
            out[cik].append(sym)
    return out


def shares_rows(z: zipfile.ZipFile, cik: str, tickers: list[str]) -> list[tuple]:
    try:
        facts = json.loads(z.read(f"CIK{cik.zfill(10)}.json")).get("facts", {})
    except KeyError:
        return []
    for ns, concept in CONCEPTS:
        units = facts.get(ns, {}).get(concept, {}).get("units", {}).get("shares")
        if units:
            return [(sym, cik, u["end"], u["filed"], float(u["val"]), u.get("form"), concept)
                    for u in units if u.get("end") and u.get("filed") and u.get("val") for sym in tickers]
    return []


def main() -> int:
    wanted = {r[0] for r in catalyst_db().execute("SELECT DISTINCT ticker FROM targets")}
    mapping = cik_tickers(wanted)
    rows: list[tuple] = []
    with zipfile.ZipFile(ZIP) as z:
        for cik, syms in mapping.items():
            rows += shares_rows(z, cik, syms)
    con = duckdb.connect(str(RESEARCH_DB))
    try:
        con.execute("CREATE OR REPLACE TABLE sec_shares (ticker VARCHAR, cik VARCHAR, end_d DATE, filed_d DATE, "
                    "shares DOUBLE, form VARCHAR, concept VARCHAR)")
        con.executemany("INSERT INTO sec_shares VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
        n_sym = con.execute("SELECT count(DISTINCT ticker) FROM sec_shares").fetchone()[0]
        si = REFERENCE_DIR / "short_interest.jsonl"
        con.execute(f"CREATE OR REPLACE TABLE short_interest AS SELECT ticker, CAST(settlement_date AS DATE) AS settlement_d, "
                    f"CAST(short_interest AS DOUBLE) AS short_interest, CAST(avg_daily_volume AS DOUBLE) AS avg_daily_volume, "
                    f"CAST(days_to_cover AS DOUBLE) AS days_to_cover FROM read_json_auto('{si.as_posix()}')")
        n_si = con.execute("SELECT count(*), count(DISTINCT ticker), min(settlement_d), max(settlement_d) FROM short_interest").fetchone()
    finally:
        con.close()
    print(f"sec_shares: {len(rows)} rows for {n_sym} of {len(wanted)} target tickers ({len(mapping)} CIKs); "
          f"short_interest: {n_si[0]} rows, {n_si[1]} tickers, {n_si[2]}..{n_si[3]}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
