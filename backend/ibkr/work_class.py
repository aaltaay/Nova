"""HOT vs COLD IB work classification (ADR 010).

No scheduler or loop move lives here. This module is the label SSOT so
hydrate / snapshot_quotes cannot be called HOT in a later task by accident.

Unknown labels raise -- do not default. Task 2 inventory must name every site.
"""
from __future__ import annotations

from enum import Enum


class WorkClass(str, Enum):
    HOT = "hot"
    COLD = "cold"


# Canonical labels. Aliases (after normalize) map to the same class.
_COLD: frozenset[str] = frozenset(
    {
        "snapshot_quotes",
        "reqtickersasync",
        "hydrate_rows",
        "hydrate",
        "surge_seed",
        "hod_surge_seed",
        "enrichment",
        "hod_enrichment",
        "reprice",
        "detail_reprice",
        "reqhistoricaldataasync",
        "historical",
        "chart_bars",
        "setups_stream",
        "reqcompletedordersasync",
        "completed_orders",
        "reqpositionsasync",
        "positions_refresh",
        "accountsummaryasync",
        "account_summary_refresh",
        "reqcontractdetailsasync",
        "qualify_batch",
        "discovery_qualify",
        "discovery_snapshot",
    }
)

_HOT: frozenset[str] = frozenset(
    {
        "placeorder",
        "cancelorder",
        "reqmktdata",
        "cancelmktdata",
        "reqmktdepth",
        "cancelmktdepth",
        "reqtickbytickdata",
        "canceltickbytickdata",
        "reqscannersubscription",
        "cancelscannersubscription",
        "connectasync",
        "disconnect",
        "reconnect",
        "reqmarketdatatype",
        "qualify_hot",
        "qualify_l1",
        "positions",
        "portfolio",
        "opentrades",
        "trades",
        "fills",
        "orderstatus",
        "execdetails",
    }
)


def normalize_label(label: str) -> str:
    return "".join(ch for ch in str(label).strip().lower() if ch.isalnum() or ch == "_")


def classify(label: str) -> WorkClass:
    """Return HOT or COLD for a work label. Unknown labels raise ValueError."""
    key = normalize_label(label)
    if not key:
        raise ValueError("work_class.classify: empty label")
    if key in _COLD:
        return WorkClass.COLD
    if key in _HOT:
        return WorkClass.HOT
    raise ValueError(f"work_class.classify: unknown label {label!r}")


def is_hot(label: str) -> bool:
    return classify(label) is WorkClass.HOT
