"""What was known about a stock-day, joined once for every search (ADR 059): shares, news, halts, relative volume.

One join and one row filter for every reader that asks "which of these stock-days": ``stock_days`` (find_stock_days),
the relative-volume reads (``rvol``) and the day facts export into the movers store (the desk's agent search,
``research/movers/export_day_facts.py``). Each column means the same thing wherever it shows:

  shares    ``outstanding_*``: SEC shares outstanding filed by the day (``day_movers.floats.sec_shares``: as of at
            most 120 days before it, on the day's share basis; a reused ticker reads its holder's count).
            ``enrichment_float``: the desk's enrichment snapshot that day (2026-07-28 on). ``float_shares`` /
            ``float_source``: the value on ``float_basis`` (sec_outstanding | enrichment | best).
  catalyst  the catalyst backfill's verdict for the day (``catalysts.for_pairs``); null is unknown, never no news.
  halts     the day's halts (``halts.for_pairs``): count, first halt ET, codes, LULD and news halts; null on a day
            the halt log does not cover, never 0.
  rvol      ``rvol_daily``: the day's volume over its usual whole-session volume (``rvol_days.for_pairs``); null when
            the relative-volume table does not hold the stock-day or has too little history.

``Wanted`` / ``wanted`` / ``keep`` / ``asked`` filter rows carrying these columns: the backend's
``day_movers.facts``, the rule the desk's agent search filters its exported day facts by, so both searches pass the
same stock-days. An unknown never passes a filter that asks about it: it is left out (``float_unknown`` decides for
shares) and counted in ``left_out`` where a reader reports it.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from market_reads import REPO, rvol_days  # noqa: F401  (REPO puts backend/ on sys.path)

from day_movers.facts import FLOAT_UNKNOWN, HALT_GROUPS, Wanted, asked, keep, wanted  # noqa: F401  (the one rule)

FLOAT_BASES = ("sec_outstanding", "enrichment", "best")
RVOL = ("rvol_daily", "rvol_volume", "rvol_day_avg_volume", "rvol_day_avg_sessions")
SHARES = ("outstanding_shares", "outstanding_as_of", "outstanding_filed", "outstanding_age_days", "enrichment_float",
          "float_shares", "float_source")
CATALYST = ("catalyst_verdict", "catalyst_category", "catalyst_strength", "catalyst_title", "catalyst_cutoff")
HALTS = ("halts", "first_halt_et", "halt_codes", "luld_halts", "news_halts")
COLUMNS = (*SHARES, *CATALYST, *HALTS, *RVOL)
CATALYST_RULE = "the catalyst backfill's verdict for the day; null = unknown (not covered), never no news"
HALT_RULE = ("halts counts the halts that started that day (Nasdaq's log, else IBKR's); luld_halts the LULD / "
             "volatility pauses, news_halts T1-T3 / T12; null = a day the halt log does not cover, never 0")


def _outstanding(pairs: list[tuple[str, str]]) -> dict[tuple[str, str], dict[str, Any]]:
    """The endpoint's SEC count per pair (``day_movers.floats.sec_shares``: a reused ticker reads its holder's)."""
    from day_movers import floats, store
    db = store.read_only()
    if db is None:
        return {}
    try:
        return floats.sec_shares(db, pairs)
    finally:
        db.close()


def for_pairs(pairs: Iterable[tuple[str, str]], float_basis: str = "sec_outstanding",
              parts: Iterable[str] = ("shares", "catalyst", "halts", "rvol")) -> dict[tuple[str, str], dict[str, Any]]:
    """``(day, symbol)`` -> the ``COLUMNS`` of the ``parts`` asked (shares, catalyst, halts, rvol), every pair a key.
    A part whose store is not on disk raises its reader's ``LookupError``: an absent store is never "nothing"."""
    from day_movers import floats

    from market_reads import catalysts, halts
    if float_basis not in FLOAT_BASES:
        raise ValueError(f"float_basis must be one of {', '.join(FLOAT_BASES)}")
    pairs = list(dict.fromkeys((str(d)[:10], str(s)) for d, s in pairs))
    parts = set(parts)
    out: dict[tuple[str, str], dict[str, Any]] = {pair: {} for pair in pairs}
    if not pairs:
        return out
    if "shares" in parts:
        snapshots, sec = floats.enrichment_floats(pairs), _outstanding(pairs)
        for pair, row in out.items():
            count = sec.get(pair) or {}
            row.update(outstanding_shares=count.get("shares"), outstanding_as_of=count.get("as_of"),
                       outstanding_filed=count.get("filed"), outstanding_age_days=count.get("age_days"),
                       enrichment_float=round(snapshots[pair]) if pair in snapshots else None)
            if float_basis == "enrichment" or (float_basis == "best" and pair in snapshots):
                row.update(float_shares=row["enrichment_float"],
                           float_source="enrichment_snapshot" if pair in snapshots else None)
            else:
                row.update(float_shares=row["outstanding_shares"],
                           float_source="sec_shares_outstanding" if count else None)
    if "catalyst" in parts:
        verdicts = catalysts.for_pairs(pairs)
        for pair, row in out.items():
            verdict = verdicts.get(pair) or {}
            row.update(catalyst_verdict=verdict.get("verdict"), catalyst_category=verdict.get("category"),
                       catalyst_strength=verdict.get("strength"), catalyst_title=verdict.get("title"),
                       catalyst_cutoff=verdict.get("cutoff_kind"))
    if "halts" in parts:
        stops = halts.for_pairs(pairs)
        for pair, row in out.items():
            stop = stops.get(pair) or {}
            count = stop.get("halts")
            row.update(halts=count, first_halt_et=stop.get("first_halt_et"),
                       halt_codes=",".join(stop.get("codes") or []) or None,
                       luld_halts=None if count is None else stop.get("luld"),
                       news_halts=None if count is None else stop.get("news"))
    if "rvol" in parts:
        volumes = rvol_days.for_pairs(pairs)
        for pair, row in out.items():
            volume = volumes.get(pair) or {}
            row.update({key: volume.get(key) for key in RVOL})
    return out
