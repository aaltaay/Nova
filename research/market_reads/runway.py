"""Cash runway, share-count growth and offering filings through the front door (ADR 059, #1102): what a company had
on file by a past day, in one answer, so every agent reads it the same way.

Composed from three existing reads and nothing else (never a new reader of a raw store):
  reference.financials   the newest balance sheet (cash, short-term investments) and the newest quarterly cash-flow
                         statement (operating cash flow), each counted from its ``filing_date``.
  sec.shares_as_of       the shares outstanding by the day and by the day 12 and 24 months earlier, so growth over
                         4 and 8 quarters; the older count is put on the day's share basis through ``splits.factor``.
  sec.filings            the shelf / offering filings filed in the window before the day.

Rules (``architecture/schema/agent-desk.md``, "The data front door over MCP"): every figure names its statement's
period and filing date; a figure the files do not give is None, never 0; the wording is counts, dates and ratios and
no verdict. Massive dates a period by the newest filing that carried it (87% of quarterly cash-flow rows are dated
300+ days after their period), so the newest statement known on a past day is often old: ``age_days`` / ``stale`` say
so, and a runway is only divided out when the cash and the burn are from one quarter.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Any

import pandas as pd

from market_reads import reference, sec, splits, tickers

MONTHS_PER_QUARTER = 3
PERIOD_TOLERANCE_DAYS = 100          # two dates within this of the same period (a quarter + filing lag) match
STALE_AFTER_DAYS = 180               # a statement over two quarters old on the day
DEFAULT_LOOKBACK_DAYS = 1095         # the "Dilution on file" row's longest window (a shelf, 3 years)
MAX_LOOKBACK_DAYS = 3650
MAX_FILINGS = 100                    # filings listed (newest first); counts / latest cover all of them
RECENT_QUARTERS = 4
GROWTH_MONTHS = {"growth_4q": 12, "growth_8q": 24}
DAYS_PER_MONTH = 30.4375
OPERATING_CASH_FLOW_FIELDS = ("net_cash_from_operating_activities",
                              "cash_from_operating_activities_continuing_operations")
KIND_BY_FORM = {**dict.fromkeys(("S-1", "S-1/A", "F-1", "F-1/A"), "s1"),
                **dict.fromkeys(("S-3", "S-3/A", "S-3ASR", "F-3", "F-3/A", "F-3ASR"), "shelf"),
                **dict.fromkeys(("424B1", "424B2", "424B3", "424B4", "424B5"), "prospectus"),
                "8-K": "current_report"}
FORMS = tuple(KIND_BY_FORM)
RULE = ("a statement or filing counts from the day it was filed; runway = liquid cash / (cash used in operations in "
        f"the newest quarter / {MONTHS_PER_QUARTER}), only when the cash and the burn are within "
        f"{PERIOD_TOLERANCE_DAYS} days of one period")
UNITS = ("amounts are the statements' own (the dump has no currency field; months and pct do not depend on it); "
         "shares are shares; pct is percent points")


def _num(value: Any) -> float | None:
    return None if value is None or pd.isna(value) else float(value)


def _int(value: Any) -> int | None:
    return None if value is None or pd.isna(value) else int(value)


def _text(value: Any) -> str | None:
    return None if value is None or pd.isna(value) else str(value)


def _age(day: str, period_end: str) -> int:
    return (date.fromisoformat(day) - date.fromisoformat(period_end)).days


def _known(frame: pd.DataFrame, day: str) -> tuple[pd.DataFrame, int]:
    """The statements usable on ``day``, and how many rows were dropped: a period that had not ended by the day, or
    that ends after the filing that carries it, is a data error and counts for nothing."""
    if frame.empty:
        return frame, 0
    dates = {column: frame[column].map(lambda v: (_text(v) or "")[:10]) for column in ("period_end", "filing_date")}
    frame = frame.assign(**dates)
    ok = (frame["period_end"] != "") & (frame["period_end"] <= day) & (frame["period_end"] <= frame["filing_date"])
    return frame[ok], int((~ok).sum())


def _newest(frame: pd.DataFrame) -> pd.Series:
    keys = [c for c in ("period_end", "filing_date", "timeframe") if c in frame]
    return frame.sort_values(keys).iloc[-1]


def _statement(row: pd.Series, day: str) -> dict[str, Any]:
    """The labels every figure carries: its period, the day it was filed, and how old the period is on ``day``."""
    age = _age(day, row["period_end"])
    return {"period_end": row["period_end"], "filing_date": row["filing_date"], "age_days": age,
            "stale": age > STALE_AFTER_DAYS}


def _cash(balance: pd.DataFrame, day: str) -> dict[str, Any] | None:
    if balance.empty:
        return None
    row = _newest(balance)
    cash, invested = _num(row.get("cash_and_equivalents")), _num(row.get("short_term_investments"))
    if cash is None:
        liquid, basis = None, "cash_and_equivalents not reported"
    elif invested is None:
        liquid, basis = cash, "cash_and_equivalents only: no short-term investments reported"
    else:
        liquid, basis = cash + invested, "cash_and_equivalents + short_term_investments"
    return {"cash_and_equivalents": cash, "short_term_investments": invested, "liquid": liquid,
            "liquid_basis": basis, "timeframe": _text(row.get("timeframe")), **_statement(row, day)}


def _operating_cash_flow(row: pd.Series) -> tuple[float | None, str | None]:
    for field in OPERATING_CASH_FLOW_FIELDS:
        value = _num(row.get(field))
        if value is not None:
            return value, field
    return None, None


def _burn(flows: pd.DataFrame, day: str) -> dict[str, Any] | None:
    """The newest quarterly cash-flow statement: Massive's quarterly rows are stand-alone quarters."""
    if flows.empty or "timeframe" not in flows:
        return None
    quarters = flows[flows["timeframe"] == "quarterly"]
    if quarters.empty:
        return None
    ordered = quarters.sort_values(["period_end", "filing_date"])
    row = ordered.iloc[-1]
    flow, field = _operating_cash_flow(row)
    recent = [{"period_end": r["period_end"], "filing_date": r["filing_date"],
               "operating_cash_flow": _operating_cash_flow(r)[0]}
              for _, r in ordered.tail(RECENT_QUARTERS).iloc[::-1].iterrows()]
    return {"operating_cash_flow": flow, "burn": -flow if flow is not None and flow < 0 else None, "field": field,
            "fiscal_year": _int(row.get("fiscal_year")), "fiscal_quarter": _int(row.get("fiscal_quarter")),
            **_statement(row, day), "recent_quarters": recent}


def _runway(cash: dict | None, burn: dict | None) -> dict[str, Any]:
    known = [block for block in (cash, burn) if block]
    out: dict[str, Any] = {"months": None, "status": None, "period_gap_days": None,
                           "stale": any(block["stale"] for block in known) if known else None,
                           "basis": f"cash.liquid / (burn.burn / {MONTHS_PER_QUARTER})",
                           "max_period_gap_days": PERIOD_TOLERANCE_DAYS}
    if cash and burn:
        out["period_gap_days"] = (date.fromisoformat(cash["period_end"])
                                  - date.fromisoformat(burn["period_end"])).days
    if cash is None:
        out["status"] = "no_balance_sheet"
    elif burn is None:
        out["status"] = "no_cash_flow_statement"
    elif burn["operating_cash_flow"] is None:
        out["status"] = "operating_cash_flow_not_reported"
    elif burn["burn"] is None:
        out["status"] = "no_burn"
    elif cash["liquid"] is None:
        out["status"] = "cash_not_reported"
    elif abs(out["period_gap_days"]) > PERIOD_TOLERANCE_DAYS:
        out["status"] = "periods_far_apart"
    else:
        out["status"] = "computed"
        out["months"] = round(cash["liquid"] / (burn["burn"] / MONTHS_PER_QUARTER), 1)
    return out


def _months_before(day: str, months: int) -> str:
    d = date.fromisoformat(day)
    year, month = divmod(d.year * 12 + d.month - 1 - months, 12)
    month += 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1])).isoformat()


def _count(found: dict[str, Any] | None) -> dict[str, Any] | None:
    return None if found is None else {k: found[k] for k in ("value", "end", "filed", "form")}


def _growth(symbol: str, day: str, cik: str, now: dict | None, months: int) -> dict[str, Any]:
    """Shares outstanding by ``day`` against the same read ``months`` earlier, both on ``day``'s share basis."""
    out: dict[str, Any] = {"pct": None, "status": None, "months_back": months, "from": None, "to": _count(now),
                           "span_days": None}
    if now is None:
        out["status"] = "no_count_now"
        return out
    prior_day = _months_before(day, months)
    then = sec.shares_as_of(symbol, prior_day, cik=cik).get("outstanding")
    if then is None:
        out["status"] = "no_count_then"
        return out
    k = splits.factor(symbol, prior_day, as_of=day, cik=cik)
    out["from"] = {**_count(then), "value": round(then["value"] / k), "split_factor": k}
    out["span_days"] = (date.fromisoformat(now["end"]) - date.fromisoformat(then["end"])).days
    if out["span_days"] <= 0:
        out["status"] = "same_count"           # no newer count was filed in the window: unknown, not 0
    elif abs(out["span_days"] - round(months * DAYS_PER_MONTH)) > PERIOD_TOLERANCE_DAYS:
        out["status"] = "span_off_window"      # a filing gap (e.g. a cover page with two classes) leaves no count
    elif out["from"]["value"] <= 0:
        out["status"] = "count_then_not_positive"
    else:
        out["status"] = "computed"
        out["pct"] = round((now["value"] / out["from"]["value"] - 1) * 100, 2)
    return out


def _offerings(symbol: str, day: str, cik: str, lookback_days: int, notes: list[str]) -> dict[str, Any] | None:
    start = (date.fromisoformat(day) - timedelta(days=lookback_days)).isoformat()
    try:
        frame = sec.filings(symbol, day, list(FORMS), cik=cik)
    except LookupError as exc:
        notes.append(f"offerings unknown: {exc}")
        return None
    frame = frame[frame["filed"].map(lambda v: _text(v) or "") >= start]
    newest_first = frame.sort_values(["filed", "form"], ascending=False)
    listed = [{"form": r["form"], "kind": KIND_BY_FORM.get(str(r["form"]).upper()), "filed": r["filed"],
               "report_date": _text(r["report_date"]), "accession": _text(r["accession"]),
               "items": _text(r["items"])} for _, r in newest_first.head(MAX_FILINGS).iterrows()]
    counts = {f: int((frame["form"] == f).sum()) for f in FORMS if (frame["form"] == f).any()}
    latest = {f: str(frame.loc[frame["form"] == f, "filed"].max()) for f in counts}
    return {"lookback_days": lookback_days, "from": start, "through": day, "forms": list(FORMS), "total": len(frame),
            "counts": counts, "latest": latest, "filings": listed, "truncated": len(frame) > MAX_FILINGS}


def _notes(day: str, cash: dict | None, burn: dict | None, runway: dict, dropped: int) -> list[str]:
    notes = []
    if dropped:
        notes.append(f"{dropped} statement rows dropped: a period after {day} or after the filing that carries it")
    for label, block in (("balance sheet", cash), ("cash-flow statement", burn)):
        if block and block["stale"]:
            notes.append(f"the newest {label} counted on {day} is for {block['period_end']}, {block['age_days']} days "
                         f"earlier (filed {block['filing_date']}): Massive dates a period by the newest filing that "
                         "carried it, so a quarter first reported since can be absent")
    if runway["status"] == "periods_far_apart":
        notes.append(f"cash is from {cash['period_end']} and the operating cash flow from {burn['period_end']}: not "
                     f"one quarter (over {PERIOD_TOLERANCE_DAYS} days apart), so no runway is divided out")
    return notes


def runway(symbol: str, day: str, cik: str | None = None, lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> dict[str, Any]:
    """``symbol``'s cash, burn, runway, share growth and offering filings as known on ``day`` (the answer's shape is
    ``architecture/schema/agent-desk.md``, "The data front door over MCP"). The company is the one that held the
    ticker on ``day`` (``cik`` overrides; an unsettled day refuses with the candidates)."""
    date.fromisoformat(day)
    if not 1 <= lookback_days <= MAX_LOOKBACK_DAYS:
        raise ValueError(f"lookback_days must be 1 to {MAX_LOOKBACK_DAYS}")
    held = tickers.require(symbol, day, cik)
    cik = held["cik"]
    balance, dropped_balance = _known(reference.financials(symbol, "balance_sheets", day, cik=cik), day)
    flows, dropped_flows = _known(reference.financials(symbol, "cash_flow_statements", day, cik=cik), day)
    cash, burn = _cash(balance, day), _burn(flows, day)
    figures = _runway(cash, burn)
    notes = _notes(day, cash, burn, figures, dropped_balance + dropped_flows)
    now = sec.shares_as_of(symbol, day, cik=cik)
    shares = {"outstanding": now.get("outstanding"),
              **{name: _growth(symbol, day, cik, now.get("outstanding"), months)
                 for name, months in GROWTH_MONTHS.items()}}
    offerings = _offerings(symbol, day, cik, lookback_days, notes)
    return {"symbol": symbol.upper(), "day": day, "cik": cik, "entity": held["name"], "ticker": tickers.summary(held),
            "rule": RULE, "units": UNITS, "cash": cash, "burn": burn, "runway": figures, "shares": shares,
            "offerings": offerings, "notes": notes}
