"""A trade as the page reads it (ADR 066): the report's row as filed, plus what is derived from it. Pure.

Derived on every load, never stored, so a better rule needs no re-reading (architecture/schema/congress.md, "A
trade"): ``kind`` (stock / option / other), ``side`` and ``partial``, ``gift`` (a contribution is not a sale), the
amount's ``low`` / ``high``, ``owner``, and ``lag_days`` from the trade to its report (``late`` past the law's 45 days).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from congress.constants_congress import CONGRESS_GIFT_WORDS, CONGRESS_LATE_DAYS

GIFT = re.compile(CONGRESS_GIFT_WORDS, re.I)
DOLLARS = re.compile(r"\$\s*([\d,]+(?:\.\d+)?)")
HOUSE_KIND = {"ST": "stock", "OP": "option"}
SENATE_KIND = {"Stock": "stock", "Stock Option": "option"}
HOUSE_SIDE = {"P": ("buy", False), "S": ("sell", False), "S (partial)": ("sell", True), "E": ("exchange", False)}
SENATE_SIDE = {"Purchase": ("buy", False), "Sale (Full)": ("sell", False), "Sale (Partial)": ("sell", True),
               "Exchange": ("exchange", False)}
OWNERS = ("self", "spouse", "joint", "child")


@dataclass(frozen=True)
class Trade:
    id: str                     # "<report id>#<n>"
    report: str
    chamber: str                # "house" | "senate"
    bioguide: str | None
    filer: str                  # the name as filed
    filed: str                  # the report's date (a Senate amendment: the report it corrects)
    tx: str
    notified: str | None
    lag_days: int | None
    late: bool
    owner: str
    ticker: str | None
    asset: str
    asset_type: str | None
    kind: str                   # "stock" | "option" | "other"
    side: str                   # "buy" | "sell" | "exchange" | "other"
    partial: bool
    gift: bool
    amount: str                 # as filed
    low: int | None
    high: int | None
    description: str
    status: str | None          # House filing status, lower case: "new" | "amended"
    url: str


def kind_of(chamber: str, asset_type: str | None) -> str:
    table = HOUSE_KIND if chamber == "house" else SENATE_KIND
    return table.get((asset_type or "").strip(), "other")


def side_of(chamber: str, tx_type: str) -> tuple[str, bool]:
    table = HOUSE_SIDE if chamber == "house" else SENATE_SIDE
    return table.get(" ".join((tx_type or "").split()), ("other", False))


def amount_range(text: str) -> tuple[int | None, int | None]:
    """The range a report states: two figures are low and high; one with "Over" is low with no high; one alone is
    both. Dollars, rounded down to the dollar."""
    figures = [int(float(x.replace(",", ""))) for x in DOLLARS.findall(text or "")]
    if len(figures) >= 2:
        return figures[0], figures[1]
    if len(figures) == 1:
        return (figures[0], None) if "over" in text.lower() else (figures[0], figures[0])
    return None, None


def owner_of(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    return value if value in OWNERS else "self"


def is_gift(description: str) -> bool:
    return bool(GIFT.search(description or ""))


def ticker_of(raw: str | None) -> str | None:
    value = (raw or "").strip().upper().replace("/", ".")
    return value or None


def lag_days(filed: str, tx: str) -> int | None:
    try:
        return (date.fromisoformat(filed) - date.fromisoformat(tx)).days
    except ValueError:
        return None


def build(report: dict, row: dict) -> Trade:
    """One trade from its stored report and row (store.py's dicts)."""
    chamber = report["chamber"]
    side, partial = side_of(chamber, row["tx_type"])
    low, high = amount_range(row["amount"])
    lag = lag_days(report["filed"], row["tx"])
    description = row.get("description") or ""
    status = (row.get("status") or "").strip().lower() or None
    return Trade(id=f"{report['id']}#{row['n']}", report=report["id"], chamber=chamber, bioguide=report.get("bioguide"),
                 filer=report.get("filer_name") or "", filed=report["filed"], tx=row["tx"], notified=row.get("notified"),
                 lag_days=lag, late=lag is not None and lag > CONGRESS_LATE_DAYS, owner=owner_of(row.get("owner")),
                 ticker=ticker_of(row.get("ticker")), asset=row.get("asset") or "", asset_type=row.get("asset_type"),
                 kind=kind_of(chamber, row.get("asset_type")), side=side, partial=partial, gift=is_gift(description),
                 amount=row.get("amount") or "", low=low, high=high, description=description, status=status,
                 url=report["url"])


def tradable(t: Trade) -> bool:
    """Counts for "Most traded": a stock or option bought or sold, with a ticker, and not a gift."""
    return t.kind in ("stock", "option") and t.side in ("buy", "sell") and bool(t.ticker) and not t.gift


def wire(t: Trade) -> dict:
    return {"id": t.id, "report": t.report, "chamber": t.chamber, "bioguide": t.bioguide, "filer": t.filer,
            "filed": t.filed, "tx": t.tx, "notified": t.notified, "lag_days": t.lag_days, "late": t.late,
            "owner": t.owner, "ticker": t.ticker, "asset": t.asset, "asset_type": t.asset_type, "kind": t.kind,
            "side": t.side, "partial": t.partial, "gift": t.gift,
            "amount": {"text": t.amount, "low": t.low, "high": t.high}, "description": t.description,
            "status": t.status, "url": t.url}
