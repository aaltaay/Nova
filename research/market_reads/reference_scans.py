"""Cross-stock scans of Massive's reference dump (ADR 059): every stock's FINRA short interest at one settlement, and
every listed company in an SEC SIC industry. ``reference.py`` answers one stock; these answer "which stocks".

Short interest: FINRA's twice-monthly settlements, one file per settlement month
(``<NOVA_MARKET_DATA_DIR>/store/reference/short_interest/<YYYY-MM>.jsonl``, about 45,000 rows and 5.7 MB a month,
read whole: well under a second). A scan reads ONE settlement: the one named, or the newest that counts by a day by
``backend/move_reason/short_interest.counts_from`` (its ``MOVE_FINRA_PUBLISH_BUSINESS_DAYS``th business day on; the
rule ``reference.short_interest`` reads; the lag counts whole business days, so ``at`` names the moment but no time
of day changes the pick, as there). A stock absent from that settlement is absent, never filled from an older one. Tickers stay as FINRA's file writes them (``ABRpD``); each row names the company that held the ticker on the
settlement day (``tickers.resolve``), so a ticker two companies used is never merged.

Sectors: the SIC code and description in Massive's ticker details (``reference.ticker_details_all``) -- the dump's
LATEST values, not a past day's, and only for tickers active when the dump was taken (13,901 rows have details,
6,032 a SIC): a delisted company has no SIC here.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any

import pandas as pd

from market_reads import reference, tickers
from market_reads.sec_scan import sic_codes, sic_matches

SHORT_COLUMNS = ["ticker", "cik", "company", "type", "settlement_date", "short_interest", "avg_daily_volume",
                 "days_to_cover", "counts_from", "ticker_warning"]
SHORT_SORTS = {"short_interest": ("short_interest", False), "days_to_cover": ("days_to_cover", False),
               "ticker": ("ticker", True)}
SECTOR_COLUMNS = ["ticker", "name", "cik", "sic", "sic_description", "exchange", "list_date", "type", "active"]
KIND_WORDS = ("common", "all")


def kinds_set(kinds: list[str] | str | None) -> set[str] | None:
    """The security types a scan keeps: ``None`` / ``["common"]`` common stock (``tickers.COMMON_TYPES``),
    ``["all"]`` every kind (``None`` returned), else the listed Massive types (CS, ADRC, ETF, WARRANT, PFD ...)."""
    items = [p.strip() for k in ([kinds] if isinstance(kinds, str) else kinds or []) for p in str(k).split(",")
             if p.strip()]
    words = [k.lower() for k in items if k.lower() in KIND_WORDS]
    if words and len(items) > 1:
        raise ValueError(f"kinds: {words[0]!r} stands alone (a list of types, or one of {', '.join(KIND_WORDS)})")
    if words == ["all"]:
        return None
    return set(tickers.COMMON_TYPES) if not items or words else {k.upper() for k in items}


def _month_rows(month: str) -> dict[str, list[dict[str, Any]]]:
    """One settlement month's rows by settlement date; {} when the month has no file."""
    from move_reason import short_interest as finra
    path = finra.directory() / f"{month}.jsonl"
    out: dict[str, list[dict[str, Any]]] = {}
    if not path.is_file():
        return out
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                row = json.loads(line) if line.strip() else None
            except ValueError:
                continue
            if row and row.get("settlement_date") and row.get("ticker"):
                out.setdefault(str(row["settlement_date"])[:10], []).append(row)
    return out


def _settlement(settlement: str | None, day: str | None, at: str) -> tuple[str, list[dict], dict[str, Any]]:
    """``(settlement, its rows, how it was picked)``: the named one, or the newest that counts on ``day``."""
    from move_reason import short_interest as finra
    if not finra.directory().is_dir():      # the per-stock read's own words for why (it answers before any date)
        raise LookupError(finra.published_at("A", 0.0).get("reason") or "no FINRA short-interest archive here")
    if (settlement is None) == (day is None):
        raise ValueError("name one of settlement (YYYY-MM-DD) or day (with at, ET HH:MM)")
    if settlement:
        wanted = date.fromisoformat(str(settlement)).isoformat()
        month = _month_rows(wanted[:7])
        if wanted not in month:
            raise LookupError(f"no FINRA settlement {wanted} on file; {wanted[:7]} has {sorted(month) or 'none'}")
        return wanted, month[wanted], {"rule": "the settlement named", "counts_from": finra.counts_from(
            date.fromisoformat(wanted)).isoformat()}
    on = date.fromisoformat(str(day))
    hh, mm = (int(x) for x in str(at).split(":"))
    if not (0 <= hh < 24 and 0 <= mm < 60):
        raise ValueError(f"at {at!r} is not an ET HH:MM")
    best, pending = None, None
    for month in finra._months(on):
        rows = _month_rows(month)
        for settled in sorted(rows, reverse=True):
            when = date.fromisoformat(settled)
            if when > on:
                continue
            start = finra.counts_from(when)
            if start <= on and (best is None or settled > best[0]):
                best = (settled, rows[settled], start)
            elif start > on and (pending is None or settled > pending["settlement_date"]):
                pending = {"settlement_date": settled, "counts_from": start.isoformat()}
        if best:
            break
    if best is None:
        raise LookupError(f"no FINRA settlement counts by {on} on file (months {', '.join(finra._months(on))})")
    return best[0], best[1], {"rule": "the newest settlement that counts by the day (publish lag "
                                      f"{finra.MOVE_FINRA_PUBLISH_BUSINESS_DAYS} business days)",
                              "day": on.isoformat(), "at": at, "counts_from": best[2].isoformat(),
                              "pending": pending}


def _kind(held: dict[str, Any], rows: list[dict[str, Any]]) -> str | None:
    """The type of the security a ticker named that day: the holder's, else the list's when its rows agree (an ETF
    Massive lists without a CIK)."""
    if held["cik"]:
        return next((c["type"] for c in held["candidates"] if c["cik"] == held["cik"]), None)
    kinds = {r.get("type") for r in rows}
    return kinds.pop() if len(kinds) == 1 else None


def short_interest_scan(settlement: str | None = None, day: str | None = None, at: str = "09:30",
                        min_shares: float | None = None, min_days_to_cover: float | None = None,
                        kinds: list[str] | str | None = None, sort: str = "short_interest") -> pd.DataFrame:
    """Every stock's short interest at one FINRA settlement (``settlement``, or the newest published by ``day`` at
    ``at`` ET), at least ``min_shares`` short and / or ``min_days_to_cover``; common stock unless ``kinds`` says
    otherwise. ``SHORT_COLUMNS``, ranked by ``sort`` (short_interest | days_to_cover, largest first; ticker)."""
    if sort not in SHORT_SORTS:
        raise ValueError(f"sort must be one of {', '.join(SHORT_SORTS)}")
    keep = kinds_set(kinds)
    settled, rows, picked = _settlement(settlement, day, at)
    counts_from = picked["counts_from"]
    out, left_out, listed = [], {"other_kind": 0, "unknown_kind": 0}, tickers.listings()
    for row in rows:
        shares, dtc = row.get("short_interest"), row.get("days_to_cover")
        if min_shares is not None and (shares is None or shares < min_shares):
            continue
        if min_days_to_cover is not None and (dtc is None or dtc < min_days_to_cover):
            continue
        held = tickers.resolve(str(row["ticker"]), settled)
        kind = _kind(held, listed.get(held["symbol"], []))
        if keep is not None and kind not in keep:
            left_out["other_kind" if kind else "unknown_kind"] += 1
            continue
        out.append({"ticker": row["ticker"], "cik": held["cik"], "company": held["name"], "type": kind,
                    "settlement_date": settled, "short_interest": shares, "avg_daily_volume": row.get("avg_daily_volume"),
                    "days_to_cover": dtc, "counts_from": counts_from,
                    "ticker_warning": held["warning"] or (None if held["cik"] else held["rule"])})
    column, ascending = SHORT_SORTS[sort]
    frame = pd.DataFrame(out, columns=SHORT_COLUMNS)
    frame = frame.sort_values([column, "ticker"], ascending=[ascending, True], na_position="last",
                              kind="stable").reset_index(drop=True)
    frame.attrs.update(dataset="short_interest", settlement_date=settled, picked=picked, rows_in_settlement=len(rows),
                       min_shares=min_shares, min_days_to_cover=min_days_to_cover,
                       kinds=sorted(keep) if keep is not None else "all", left_out=left_out,
                       rule="one FINRA settlement for every row; a settlement counts only after its publish lag",
                       note="a stock absent from the settlement is absent, not read from an older one; tickers as "
                            "FINRA's file writes them, each row's company is the ticker's holder on the settlement day; "
                            "unknown_kind counts tickers Massive's list does not type (mostly OTC foreign ordinaries); "
                            "days_to_cover 999.99 is FINRA's cap when average volume is near zero")
    return frame


def sector_scan(sic: list[str] | str | int | None = None, sic_words: list[str] | str | None = None,
                exchange: list[str] | str | None = None, active: bool | None = None,
                kinds: list[str] | str | None = None) -> pd.DataFrame:
    """Every ticker whose SIC is in ``sic`` (``2834``; ``283*`` a prefix) OR whose SIC description contains any of
    ``sic_words`` (any case), on ``exchange`` (primary exchange: XNAS, XNYS, XASE ...) when given; common stock unless
    ``kinds`` says otherwise. ``SECTOR_COLUMNS``, by SIC then ticker. The dump's latest SIC, not a past day's."""
    codes = sic_codes(sic)
    words = [w.strip().lower() for w in ([sic_words] if isinstance(sic_words, str) else sic_words or []) if w.strip()]
    if not codes and not words:
        raise ValueError("a sector scan names sic codes (2834, or 283* for a prefix) or sic_words (e.g. pharmaceutical)")
    exchanges = {e.strip().upper() for e in ([exchange] if isinstance(exchange, str) else exchange or []) if e.strip()}
    keep = kinds_set(kinds)
    details = reference.ticker_details_all()
    named = [c for c in ("sic_code", "sic_description") if c in details]
    details = details[details[named].notna().any(axis=1)] if named else details.iloc[0:0]
    out = []
    for rec in details.to_dict("records"):
        code = rec.get("sic_code")
        code = None if code is None or code != code else str(code).strip()
        description = rec.get("sic_description") if isinstance(rec.get("sic_description"), str) else None
        if not (sic_matches(code, codes) or (description and any(w in description.lower() for w in words))):
            continue
        is_active = str(rec.get("active")) == "True"      # True / numpy True; NaN where the dump has no details
        if (exchanges and str(rec.get("primary_exchange") or "").upper() not in exchanges) or (
                active is not None and is_active != active) or (keep is not None and rec.get("type") not in keep):
            continue
        out.append({"ticker": rec.get("ticker"), "name": rec.get("name"), "cik": tickers._cik(
            rec.get("cik") if isinstance(rec.get("cik"), str) else None), "sic": code.zfill(4) if code else None,
            "sic_description": description, "exchange": rec.get("primary_exchange"),
            "list_date": rec.get("list_date") if isinstance(rec.get("list_date"), str) else None,
            "type": rec.get("type"), "active": is_active})
    frame = pd.DataFrame(out, columns=SECTOR_COLUMNS).sort_values(["sic", "ticker"]).reset_index(drop=True)
    frame.attrs.update(dataset="ticker_details", sic=codes or None, sic_words=words or None,
                       exchange=sorted(exchanges) or None, active=active,
                       kinds=sorted(keep) if keep is not None else "all", as_of="latest_only",
                       rule="SIC codes OR description words (any); a code ending * is a prefix",
                       note="SIC is the reference dump's latest, not as of a past day; the dump holds ticker details "
                            "only for tickers active when it was taken, so a delisted company is not here")
    return frame
