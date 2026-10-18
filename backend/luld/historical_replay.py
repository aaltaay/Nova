"""Historical Sim selection adapter for LULD replay (ADR 046, ADR 047, #775, #825).

Adapts the loaded historical window (``sim.history_playback.selected()``, whether a Massive flat-file
import or an IBKR historical download) into the event stream and facts that ``luld.replay`` feeds
into ``Tracker`` up to the Sim playhead.

Reads the selection's ``PrintTable`` columns and ``QuoteSeries`` arrays directly without materializing
per-print dicts, translates Massive numeric sale conditions (17 -> ``O``, 18 -> ``5``), deduplicates
unchanged ``(bid, ask)`` NBBO updates, keeps quote-less windows approximate (``allow_exact=False``),
and never substitutes today's live market cap or index membership on a past session.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from constants_sim import SIM_MASSIVE_SOURCE
from luld import rules
from luld.study import MASSIVE_OPEN_CODES, MASSIVE_REOPEN_CODES
from luld.tracker import DEFAULT_OPTIONS, Facts, Options
from sale_conditions import row_sets_price
from sim.massive_files import condition_codes

_ACTIVE_DOWNLOAD = ("queued", "running")


@dataclass(frozen=True)
class HistoricalData:
    key: str
    symbol: str
    date: str
    source: str
    prints: Any
    quotes: Any
    prev_close: float | None
    spans: list[tuple[float, float]]
    has_prints: bool
    has_quotes: bool
    empty_reason: str | None = None
    empty_state: str = "unknown"


def from_selection(selection: Any) -> HistoricalData | None:
    """Wrap ``sim.history_playback.selected()`` for ``luld.replay``, or ``None`` when nothing is loaded."""
    if selection is None:
        return None
    spec = getattr(selection, "spec", None) or {}
    symbol = str(spec.get("symbol") or "").strip().upper()
    if not symbol:
        return None
    date = str(spec.get("date") or "")
    source = str(spec.get("source") or "ibkr")
    prints = getattr(selection, "prints", None)
    quotes = getattr(selection, "quotes", None)
    n_prints = len(prints) if prints is not None else 0
    n_quotes = len(quotes) if quotes is not None else 0
    has_prints = n_prints > 0
    has_quotes = n_quotes > 0
    spans = [(float(a), float(b)) for a, b in (spec.get("coverage") or [])]
    status = spec.get("download_status")
    empty_reason = None
    empty_state = "unknown"
    if not has_prints and not has_quotes:
        if status in _ACTIVE_DOWNLOAD:
            empty_state = "warming"
            empty_reason = "Loading the historical replay's trades for the LULD band"
        else:
            empty_reason = "This historical replay has no trades loaded for the LULD band"
    key = (
        f"{date}|{symbol}|{spec.get('start')}|{spec.get('end')}|{source}|"
        f"{spec.get('job_id')}|{n_prints}|{n_quotes}|{spec.get('quote_status')}"
    )
    return HistoricalData(
        key=key,
        symbol=symbol,
        date=date,
        source=source,
        prints=prints,
        quotes=quotes,
        prev_close=getattr(selection, "prev_close", None),
        spans=spans,
        has_prints=has_prints,
        has_quotes=has_quotes,
        empty_reason=empty_reason,
        empty_state=empty_state,
    )


def _print_meta(source: str):
    massive = source == SIM_MASSIVE_SOURCE

    def judge(fields: dict[str, Any]) -> tuple[bool, str, str]:
        raw_cond = str(fields.get("conditions") or "")
        if massive:
            codes = condition_codes(raw_cond)
            cond = ("O" if codes & MASSIVE_OPEN_CODES else "") + ("5" if codes & MASSIVE_REOPEN_CODES else "")
        else:
            cond = raw_cond
        return row_sets_price(fields), cond, str(fields.get("exchange") or "")

    return judge


def events(data: HistoricalData) -> list[tuple]:
    """``(ts, 0, price, eligible, conditions, exchange)`` and ``(ts, 1, bid, ask)`` in time order."""
    out: list[tuple] = []
    table = data.prints
    if table is not None and len(table):
        metas = table.judged(_print_meta(data.source))
        for ts, price, (eligible, cond, ex) in zip(table.values("ts"), table.values("price"), metas, strict=True):
            if price > 0:
                out.append((float(ts), 0, float(price), eligible, cond, ex))
    quotes = data.quotes
    if quotes is not None and len(quotes):
        last_pair: tuple[float | None, float | None] | None = None
        for ts, raw_bid, raw_ask in zip(quotes.ts, quotes.bid, quotes.ask, strict=True):
            bid = None if raw_bid != raw_bid or raw_bid <= 0 else float(raw_bid)
            ask = None if raw_ask != raw_ask or raw_ask <= 0 else float(raw_ask)
            pair = (bid, ask)
            if pair == last_pair:
                continue
            last_pair = pair
            out.append((float(ts), 1, bid, ask))
    out.sort(key=lambda e: (e[0], e[1]))
    return out


def started_at(data: HistoricalData, evs: list[tuple]) -> float:
    """When the historical window began watching: the earliest of its coverage start and its first event."""
    candidates: list[float] = []
    if data.spans:
        candidates.append(float(data.spans[0][0]))
    if evs:
        candidates.append(float(evs[0][0]))
    return min(candidates) if candidates else time.time()


def facts(data: HistoricalData) -> Facts:
    """Facts for a historical session: never applies today's Yahoo market cap or index membership (#775)."""
    prev = data.prev_close
    covered, reason = rules.covered(data.symbol)
    tier, basis, sure = None, None, True
    if rules.tier_needed(prev):
        tier, basis, sure = rules.tier_from_size(None)
    elif prev is not None:
        basis = "at or under $3.00 both tiers share one band"
    return Facts(prev_close=prev, tier=tier, tier_basis=basis, tier_sure=sure, covered=covered, covered_reason=reason)


def options(data: HistoricalData) -> Options:
    """Without NBBO quotes, limit states cannot be observed, so the band stays approximate."""
    if not data.has_quotes:
        return Options(allow_exact=False)
    return DEFAULT_OPTIONS
