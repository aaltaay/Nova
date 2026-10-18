"""SEC's own numbers through the front door (ADR 059): a company's share counts and its filing list, as known on a
past day.

Two bulk files SEC publishes, under ``<NOVA_CATALYST_DIR>/edgar`` (read-only, opened once per process):
  companyfacts.zip  every XBRL fact each registrant tagged, with the period it is as of (``end``) and the day it was
                    filed (``filed``) -- shares outstanding / issued / treasury, the 10-K's public float in dollars.
  submissions.zip   every filing's form and date: 10-Q, 10-K, 20-F, 8-K, Forms 3/4/5, Schedules 13D/13G, 424B ...

A symbol becomes a CIK through Massive's ticker list (``reference/tickers.json``, delisted tickers included); a
ticker another company used first reads the current owner's facts, which the as-of window rarely lets through.
As-of rule: a fact or filing counts from the day it was filed, never from the period it describes.
"""
from __future__ import annotations

import json
import threading
import zipfile
from datetime import date
from functools import lru_cache
from typing import Any

import pandas as pd

from market_reads import roots

# (namespace, concept, unit, what it is). Shares unless the unit says USD.
SHARE_FACTS = (
    ("dei", "EntityCommonStockSharesOutstanding", "shares", "cover-page shares outstanding (10-Q / 10-K / 20-F)"),
    ("us-gaap", "CommonStockSharesOutstanding", "shares", "balance-sheet shares outstanding at period end"),
    ("us-gaap", "CommonStockSharesIssued", "shares", "balance-sheet shares issued at period end"),
    ("us-gaap", "TreasuryStockCommonShares", "shares", "treasury shares (common) at period end"),
    ("us-gaap", "TreasuryStockShares", "shares", "treasury shares at period end"),
    ("us-gaap", "WeightedAverageNumberOfSharesOutstandingBasic", "shares", "period's average shares (basic EPS)"),
    ("us-gaap", "WeightedAverageNumberOfDilutedSharesOutstanding", "shares", "period's average shares (diluted EPS)"),
    ("dei", "EntityPublicFloat", "USD", "10-K cover: dollar value held by non-affiliates at the 2nd fiscal quarter's end"),
)
OUTSTANDING = ("EntityCommonStockSharesOutstanding", "CommonStockSharesOutstanding")
DOMESTIC_ANNUAL = {"10-K", "10-K405", "10-KSB", "10-KT", "10-K/A", "10-KSB/A"}
FOREIGN_ANNUAL = {"20-F", "40-F", "20-F/A", "40-F/A"}
_LOCK = threading.Lock()


@lru_cache(maxsize=2)
def _zip(name: str) -> zipfile.ZipFile:
    path = roots.edgar() / name
    if not path.is_file():
        raise LookupError(f"{path} is not on disk (SEC bulk download: https://www.sec.gov/dera/data)")
    return zipfile.ZipFile(path)


def _member(name: str, member: str) -> dict | None:
    archive = _zip(name)
    with _LOCK:                       # one ZipFile shares one file handle: reads must not interleave
        try:
            return json.loads(archive.read(member))
        except KeyError:
            return None


@lru_cache(maxsize=1)
def _tickers() -> dict[str, str]:
    path = roots.reference() / "tickers.json"
    out: dict[str, str] = {}
    if path.is_file():
        for row in json.loads(path.read_text(encoding="utf-8")):
            ticker, cik = str(row.get("ticker") or "").strip().upper(), str(row.get("cik") or "").lstrip("0")
            if ticker and cik:
                out.setdefault(ticker, cik)
    return out


def cik_for(symbol: str) -> str | None:
    """The SEC CIK (no leading zeros) Massive's ticker list gives ``symbol``; None when it has none."""
    return _tickers().get(symbol.strip().upper())


def _require_cik(symbol: str) -> str:
    cik = cik_for(symbol)
    if not cik:
        raise LookupError(f"{symbol.upper()} has no SEC CIK in {roots.reference() / 'tickers.json'}")
    return cik


def facts(symbol: str, as_of: str | None = None) -> pd.DataFrame:
    """Every share fact (``SHARE_FACTS``) ``symbol``'s company tagged, filed on or before ``as_of`` when given:
    ``concept, unit, end (as of), filed, value, form, fy, fp, accn``, oldest first."""
    cik = _require_cik(symbol)
    doc = _member("companyfacts.zip", f"CIK{cik.zfill(10)}.json") or {}
    rows = []
    for namespace, concept, unit, _what in SHARE_FACTS:
        for fact in ((doc.get("facts") or {}).get(namespace, {}).get(concept, {}).get("units", {}).get(unit) or []):
            if as_of and str(fact.get("filed") or "9999") > as_of:
                continue
            rows.append({"concept": concept, "unit": unit, "end": fact.get("end"), "filed": fact.get("filed"),
                         "value": fact.get("val"), "form": fact.get("form"), "fy": fact.get("fy"),
                         "fp": fact.get("fp"), "accn": fact.get("accn")})
    frame = pd.DataFrame(rows, columns=["concept", "unit", "end", "filed", "value", "form", "fy", "fp", "accn"])
    if len(frame):
        frame = frame.sort_values(["concept", "end", "filed"]).reset_index(drop=True)
    frame.attrs.update(symbol=symbol.upper(), cik=cik, as_of=as_of or "latest", entity=doc.get("entityName"),
                       rule="a fact counts from the day it was filed")
    return frame


def _share_factor(symbol: str, after: str, through: str) -> float:
    """Shares counted on ``after`` -> ``through``'s share basis (a 1-for-10 reverse split divides by 10)."""
    from market_reads import splits
    rows = splits.table(symbol)
    a, t = date.fromisoformat(after), date.fromisoformat(through)
    picked = rows[(rows["execution_date"] > a) & (rows["execution_date"] <= t)]
    return float((1.0 / picked["price_factor"]).prod()) if len(picked) else 1.0


def shares_as_of(symbol: str, day: str, max_age_days: int | None = None) -> dict[str, Any]:
    """What SEC filings said about ``symbol``'s shares by ``day``: the newest of each concept filed by then.

    ``outstanding`` is the cover-page count (else the balance sheet's), put on ``day``'s share basis through the
    splits listed in between; ``issued`` / ``treasury`` / ``public_float_usd`` as filed. Each value carries its
    ``end`` (as of), ``filed`` and ``age_days``; ``max_age_days`` drops an older outstanding count (the day movers
    float filter uses 120). Shares issued after the filing are not in any of it."""
    frame = facts(symbol, as_of=day)

    def newest(concepts) -> dict[str, Any] | None:
        pick = frame[frame["concept"].isin(concepts)] if len(frame) else frame
        pick = pick[pick["end"].notna() & (pick["end"] <= day)] if len(pick) else pick
        if not len(pick):
            return None
        row = pick.sort_values(["end", "filed"]).iloc[-1]
        age = (date.fromisoformat(day) - date.fromisoformat(row["end"])).days
        return {"value": float(row["value"]), "concept": row["concept"], "end": row["end"], "filed": row["filed"],
                "form": row["form"], "age_days": age}

    out = {"symbol": symbol.upper(), "day": day, "cik": frame.attrs.get("cik"), "entity": frame.attrs.get("entity"),
           "rule": "newest fact filed on or before the day; outstanding split-adjusted to the day's basis"}
    for concepts in OUTSTANDING:          # the cover page when it has one, else the balance sheet
        out["outstanding"] = newest([concepts])
        if out["outstanding"]:
            break
    if out["outstanding"] and max_age_days is not None and out["outstanding"]["age_days"] > max_age_days:
        out["outstanding"] = None
    if out["outstanding"]:
        k = _share_factor(symbol, out["outstanding"]["end"], day)
        out["outstanding"].update(split_factor=k, value=round(out["outstanding"]["value"] * k))
    out["issued"] = newest(["CommonStockSharesIssued"])
    out["treasury"] = newest(["TreasuryStockCommonShares", "TreasuryStockShares"])
    out["public_float_usd"] = newest(["EntityPublicFloat"])
    out["filer"] = filer_kind(symbol, day)
    return out


def filings(symbol: str, as_of: str | None = None, forms: list[str] | None = None) -> pd.DataFrame:
    """``symbol``'s company's filings (form, filing date, report date, accession), filed on or before ``as_of``,
    only ``forms`` when given (``["4", "SC 13D", "SCHEDULE 13G", "424B4", "8-K"]``), oldest first."""
    cik = _require_cik(symbol)
    doc = _member("submissions.zip", f"CIK{cik.zfill(10)}.json") or {}
    blocks = [((doc.get("filings") or {}).get("recent")) or {}]
    for extra in (doc.get("filings") or {}).get("files") or []:
        blocks.append(_member("submissions.zip", extra.get("name", "")) or {})
    rows = []
    wanted = {f.upper() for f in forms} if forms else None
    for block in blocks:
        columns = {k: block.get(k) or [] for k in ("filingDate", "reportDate", "accessionNumber", "items")}

        def at(key: str, i: int):
            return columns[key][i] if i < len(columns[key]) else None

        for i, form in enumerate(block.get("form") or []):
            filed = at("filingDate", i)
            if (as_of and filed and filed > as_of) or (wanted and str(form).upper() not in wanted):
                continue
            rows.append({"form": form, "filed": filed, "report_date": at("reportDate", i),
                         "accession": at("accessionNumber", i), "items": at("items", i)})
    frame = pd.DataFrame(rows, columns=["form", "filed", "report_date", "accession", "items"])
    if len(frame):
        frame = frame.sort_values(["filed", "form"]).reset_index(drop=True)
    frame.attrs.update(symbol=symbol.upper(), cik=cik, as_of=as_of or "latest", entity=doc.get("name"),
                       rule="a filing counts from its filing date")
    return frame


def filer_kind(symbol: str, day: str) -> str:
    """``domestic`` (newest annual report filed by ``day`` is a 10-K), ``foreign`` (20-F / 40-F: such companies
    file no Forms 3/4/5) or ``unknown`` (none filed yet, or no CIK)."""
    try:
        annual = filings(symbol, as_of=day, forms=sorted(DOMESTIC_ANNUAL | FOREIGN_ANNUAL))
    except LookupError:
        return "unknown"
    if not len(annual):
        return "unknown"
    return "domestic" if annual.iloc[-1]["form"].upper() in DOMESTIC_ANNUAL else "foreign"
