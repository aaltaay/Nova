"""``GET /api/practice/history``: the practice ledger as history (ADR 020, the Account page).

A pure derivation from ledger events -- nothing here talks to IBKR or invents
a mark. ``equity`` is the running net liquidation *after each fill and
rollover event*, every held position marked at its own last fill price; there
is no point between events, so a flat stretch is drawn flat, and the series is
event-marked (its last point can differ from the account's live-marked
figure on ``/api/practice/account``). Fills carry the ADR 007 ``source`` and
``bot_id`` the ledger stamped, so the by-source split is read, never inferred.
Daily rows key on the practice day (``practice.clock.day_start_ts``, the 04:00
ET rollover) and include the archived Paper ledgers beside the live one,
read-only and flagged ``archived``; a damaged archive is skipped with a logged
warning and named in ``warnings``, never a 500. Sim answers from its scratch
ledger with no archives; nothing loaded is the shape with empty lists.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Iterable

from constants_practice import (
    PRACTICE_HISTORY_RANGE_ALL,
    PRACTICE_HISTORY_RANGE_DAYS,
    PRACTICE_HISTORY_RANGE_DEFAULT,
    PRACTICE_HISTORY_RANGE_YTD,
    PRACTICE_HISTORY_RANGES,
    PRACTICE_HISTORY_SCHEMA_VERSION,
)
from practice.clock import at, day_start_ts, iso_et
from practice.fees import Fees
from practice.ledger import ACCOUNT_IDS, EVENT_FILLED, EVENT_ROLLOVER, Ledger

logger = logging.getLogger(__name__)

_PLACES = 4
_BOT_SOURCE = "bot"


class RangeError(ValueError):
    """Not one of ``PRACTICE_HISTORY_RANGES``."""


# ------------------------------------------------------------------- ranges
def normalize_range(value: str | None) -> str:
    key = (value or PRACTICE_HISTORY_RANGE_DEFAULT).strip().upper()
    if key not in PRACTICE_HISTORY_RANGES:
        raise RangeError(f"range must be one of {', '.join(PRACTICE_HISTORY_RANGES)}, not {value!r}")
    return key


def range_start_ts(range_key: str, now_ts: float) -> float | None:
    """Epoch of the first practice day ``range_key`` covers, counted back from ``now_ts``'s; ``None`` for ALL."""
    if range_key == PRACTICE_HISTORY_RANGE_ALL:
        return None
    today = at(day_start_ts(now_ts))
    if range_key == PRACTICE_HISTORY_RANGE_YTD:
        return today.replace(month=1, day=1).timestamp()
    return (today - timedelta(days=PRACTICE_HISTORY_RANGE_DAYS[range_key] - 1)).timestamp()


def _in_range(ts: float, start: float | None) -> bool:
    return start is None or float(ts) >= start


def _day_of(ts: float) -> str:
    """The practice day ``ts`` belongs to, as its ET calendar date."""
    return at(day_start_ts(ts)).date().isoformat()


def _money(value: float) -> float:
    return round(float(value), _PLACES)


# ------------------------------------------------------------------- replay
class _Replay(Ledger):
    """The ledger fed one already-stamped event at a time, so the state after each can be read."""

    def push(self, event: dict[str, Any]) -> dict[str, Any] | None:
        """Apply ``event``; returns the order row it closed, when it closed one."""
        before = len(self._closed)
        self.events.append(dict(event))
        self._apply(event)
        return dict(self._closed[-1]) if len(self._closed) > before else None


@dataclass(frozen=True)
class _Walk:
    equity: list[dict[str, Any]]
    fills: list[dict[str, Any]]
    unrealized: float


def _point(replay: Ledger, ts: float) -> dict[str, Any]:
    return {
        "ts": float(ts),
        "net_liquidation": _money(replay.net_liquidation()),
        "cash": _money(replay.cash),
        "realized": _money(replay.realized),
        "unrealized": _money(replay.unrealized_pnl()),
    }


def _fill_entry(event: dict[str, Any], row: dict[str, Any], realized_delta: float) -> dict[str, Any]:
    fees = Fees.from_dict(event.get("fees"))
    bot_id = event.get("bot_id") if event.get("bot_id") is not None else row.get("bot_id")
    return {
        "ts": float(event["ts"]),
        "order_id": int(row["order_id"]),
        "symbol": str(row["symbol"]).upper(),
        "side": str(row["side"]).upper(),
        "qty": float(row["qty"]),
        "price": float(event["price"]),
        "source": event.get("source") or row.get("order_source"),
        "bot_id": bot_id,
        "commission": _money(fees.commission),
        "fees": _money(fees.sec_fee + fees.finra_taf),
        "realized": _money(realized_delta),
        "fill_estimated": True,
        "fill_basis": event.get("basis"),
    }


def _walk(ledger: Ledger) -> _Walk:
    """One pass over the events: an equity point after every fill and rollover, and every fill."""
    replay = _Replay(ledger.starting_cash, created_ts=ledger.created_ts)
    equity: list[dict[str, Any]] = []
    fills: list[dict[str, Any]] = []
    for event in ledger.events:
        before = replay.realized
        closed = replay.push(event)
        kind = event.get("type")
        if kind == EVENT_FILLED and closed is not None:
            fills.append(_fill_entry(event, closed, replay.realized - before))
        elif kind != EVENT_ROLLOVER:
            continue  # placed / replaced / cancelled / expired move no money
        equity.append(_point(replay, float(event["ts"])))
    return _Walk(equity, fills, replay.unrealized_pnl())


# --------------------------------------------------------------- aggregates
def _aggregate(fills: Iterable[dict[str, Any]]) -> dict[str, Any]:
    realized = commissions = fees = 0.0
    count = 0
    for fill in fills:
        realized += float(fill["realized"])
        commissions += float(fill["commission"])
        fees += float(fill["fees"])
        count += 1
    return {"realized": _money(realized), "fills": count, "commissions": _money(commissions), "fees": _money(fees)}


def _is_bot(fill: dict[str, Any]) -> bool:
    return fill.get("source") == _BOT_SOURCE or fill.get("bot_id") is not None


def _by_source(fills: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, Any], list[dict[str, Any]]] = {}
    for fill in fills:
        groups.setdefault((fill["source"], fill["bot_id"]), []).append(fill)
    return [
        {"source": source, "bot_id": bot_id, **_aggregate(rows)}
        for (source, bot_id), rows in groups.items()  # first-fill order
    ]


def _daily(fills: list[dict[str, Any]], *, archived: bool) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for fill in fills:
        groups.setdefault(_day_of(fill["ts"]), []).append(fill)
    return [{"date": day, **_aggregate(rows), "archived": archived} for day, rows in sorted(groups.items())]


def _components(fills: list[dict[str, Any]], unrealized: float) -> dict[str, float]:
    agg = _aggregate(fills)
    return {
        "realized": agg["realized"],
        "unrealized": _money(unrealized),
        "commissions": agg["commissions"],
        "sec_finra_fees": agg["fees"],
        "bot_realized": _money(sum(float(f["realized"]) for f in fills if _is_bot(f))),
    }


def _archive_entry(name: str, ledger: Ledger, fills: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "file": name,
        "opened_at": iso_et(ledger.created_ts),
        "closed_at": iso_et(ledger.last_event_ts()),
        "realized": _money(ledger.realized),
        "days": len({_day_of(f["ts"]) for f in fills}),
    }


# ------------------------------------------------------------------ builders
def build(
    ledger: Ledger,
    *,
    venue: str,
    range_key: str,
    now_ts: float,
    archives: Iterable[tuple[str, Ledger]] = (),
    warnings: Iterable[str] = (),
    account_id: str | None = None,
) -> dict[str, Any]:
    """The history payload for ``ledger``; ``archives`` are ``(file name, ledger)`` pairs, read-only."""
    range_key = normalize_range(range_key)
    start = range_start_ts(range_key, now_ts)
    walk = _walk(ledger)
    fills = [f for f in walk.fills if _in_range(f["ts"], start)]
    daily: list[dict[str, Any]] = []
    archived: list[dict[str, Any]] = []
    for name, old in archives:
        old_walk = _walk(old)
        archived.append(_archive_entry(name, old, old_walk.fills))
        daily.extend(_daily([f for f in old_walk.fills if _in_range(f["ts"], start)], archived=True))
    daily.extend(_daily(fills, archived=False))
    daily.sort(key=lambda d: (d["date"], not d["archived"]))
    return {
        "venue": venue,
        "account_id": account_id or ACCOUNT_IDS.get(venue),
        "range": range_key,
        "range_start": start,
        "schema_version": PRACTICE_HISTORY_SCHEMA_VERSION,
        "starting_cash": _money(ledger.starting_cash),
        "ledger_opened_at": iso_et(ledger.created_ts),
        "equity": [p for p in walk.equity if _in_range(p["ts"], start)],
        "fills": fills,
        "by_source": _by_source(fills),
        "daily": daily,
        "archives": archived,
        "components": _components(fills, walk.unrealized),
        "warnings": list(warnings),
    }


def load_archives(persist_path: str | None) -> tuple[list[tuple[str, Ledger]], list[str]]:
    """Every archived ledger beside ``persist_path``, oldest first; a damaged one becomes a warning, not a 500."""
    if not persist_path:
        return [], []
    from practice import persist

    try:
        paths = persist.list_archives(persist_path)
    except OSError as exc:
        logger.warning("PRACTICE history: cannot list archives beside %s: %s", persist_path, exc)
        return [], [f"archives beside {os.path.basename(persist_path)} could not be listed: {exc}"]
    loaded: list[tuple[str, Ledger]] = []
    warnings: list[str] = []
    for path in paths:
        name = os.path.basename(path)
        try:
            ledger = persist.load(path)
        except persist.LedgerSchemaError as exc:
            logger.warning("PRACTICE history: skipping archive %s: %s", path, exc)
            warnings.append(f"archive {name} skipped: {exc}")
            continue
        if ledger is not None:
            loaded.append((name, ledger))
    return loaded, warnings


def for_broker(broker: Any, range_value: str | None) -> dict[str, Any]:
    """The venue broker's history: its ledger, its clock, and (Paper) the archives beside its file."""
    range_key = normalize_range(range_value)
    broker.rollover()  # the same day boundary /api/practice/account records
    archives, warnings = load_archives(broker.persist_path)
    return build(
        broker.ledger,
        venue=broker.venue,
        range_key=range_key,
        now_ts=float(broker.reference.now_ts()),
        archives=archives,
        warnings=warnings,
        account_id=broker.account_id,
    )
