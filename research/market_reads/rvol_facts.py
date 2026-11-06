"""The day-fact filters and groups of the relative-volume reads (#1100 follow-up, ADR 059): news, shares and halts.

``rvol.scan``, ``rvol.triggers`` and ``rvol_outcomes.outcomes`` take find_stock_days' day-fact filters --
``catalyst`` (verdicts; ``unknown`` matches a day with none), ``catalyst_category`` (the verdict's category),
``catalyst_words`` (a headline containing any of the words), ``float_max`` on ``float_basis`` (sec_outstanding |
enrichment | best) with ``float_unknown`` (exclude | include | only), ``halted`` and ``halt_codes`` (``T1``,
``LUDP`` ...; ``news`` / ``luld`` name their groups) -- through ``day_facts``, the one join and row filter every
stock-day search uses (its docstring says what each column means). Joining costs reads, so the facts are joined only
when a filter or a group asks for them, only the parts asked (each part reads a store), only for the rows the
relative-volume filters already kept, ``BATCH`` stock-days at a time. A kept row carries the joined parts' columns.

An unknown never passes a filter that asks about it: it is left out and counted in ``left_out``
(``catalyst_unknown``: no verdict, ``shares_unknown``: no value on the basis, ``halts_unknown``: a day the halt log does
not cover), never read as no news, a small float or no halt.

Groups (``rvol_outcomes``' ``group_by``): ``catalyst`` the verdict, ``catalyst_category`` the verdict's category
(lower case; ``no category`` for a judged day without one), ``float`` the bucket of ``float_shares``
(``FLOAT_BUCKETS``). A stock-day with no value is the group ``unknown``. A control is grouped with its trigger.
"""
from __future__ import annotations

import bisect
from collections import Counter
from collections.abc import Iterable
from typing import Any

import numpy as np
import pandas as pd

from market_reads import day_facts

BATCH = 20_000                  # stock-days per day_facts.for_pairs call (each part reads its store in chunks)
PART_COLUMNS = {"shares": day_facts.SHARES, "catalyst": day_facts.CATALYST, "halts": day_facts.HALTS}
COUNTS = ("outstanding_shares", "outstanding_age_days", "enrichment_float", "float_shares", "halts", "luld_halts",
          "news_halts")         # whole numbers (Int64); every other joined column is text
GROUPS = ("catalyst", "catalyst_category", "float")
GROUP_PARTS = {"catalyst": "catalyst", "catalyst_category": "catalyst", "float": "shares"}
UNKNOWN, NO_CATEGORY = "unknown", "no category"
FLOAT_EDGES = (5_000_000, 10_000_000, 20_000_000, 50_000_000)
FLOAT_LABELS = ("<5M", "5-10M", "10-20M", "20-50M", "50M+")
FLOAT_BUCKETS = {"edges": list(FLOAT_EDGES), "labels": [*FLOAT_LABELS, UNKNOWN],
                 "rule": "float_shares on float_basis, each bucket from its lower edge up to (not including) the "
                         "next: <5M under 5,000,000 shares, 5-10M, 10-20M, 20-50M, 50M+ 50,000,000 or more; unknown "
                         "= no value on the basis (never read as a small float)"}
FLOAT_RULE = ("float_shares is the float_basis value: sec_outstanding = SEC shares outstanding filed by the day (as of "
              "<= 120 days before it, on the day's share basis) -- not free float; enrichment = the desk's own float "
              "that day (2026-07-28 on); best = enrichment, else outstanding")
JOIN_RULE = ("day facts are joined by day_facts (find_stock_days' join) for the rows the relative-volume filters "
             "kept; an unknown never passes a filter that asks about it: left out, counted in left_out")
GROUP_RULE = ("catalyst = the verdict, catalyst_category = its category (lower case; 'no category' for a judged day "
              "without one), float = the float_buckets bucket; a stock-day with no value is 'unknown' (not judged / "
              "no value on the basis), never no news or a small float; a control is grouped with its trigger")
CONTROL_RULE = "the control pool passes the same day-fact filters as the triggers (the same universe)"


def _typed(column: str, values: list[Any]):
    return pd.array(values, dtype="Int64" if column in COUNTS else "string")


def _listed(words: Iterable[str] | str | None) -> list[str] | None:
    """A word list as asked; one bare word is a list of one (never its letters)."""
    return [words] if isinstance(words, str) else None if words is None else list(words)


class Facts:
    """One read's day-fact filters (``day_facts.wanted``), the parts they and a group join, and what they left out.
    ``group_by``: an ``rvol_outcomes`` group that reads a part (``GROUP_PARTS``) without filtering on it."""

    def __init__(self, *, catalyst: Iterable[str] | None = None, catalyst_category: Iterable[str] | None = None,
                 catalyst_words: Iterable[str] | None = None, float_max: float | None = None,
                 float_basis: str = "sec_outstanding", float_unknown: str = "exclude", halted: bool | None = None,
                 halt_codes: Iterable[str] | None = None, group_by: str | None = None):
        if float_basis not in day_facts.FLOAT_BASES:
            raise ValueError(f"float_basis must be one of {', '.join(day_facts.FLOAT_BASES)}")
        if halted is not None and halted not in (True, False):
            raise ValueError("halted is true (only days with a halt) or false (only days without one)")
        self.wanted = day_facts.wanted(float_max=float_max, float_unknown=float_unknown, catalyst=_listed(catalyst),
                                       catalyst_category=_listed(catalyst_category),
                                       catalyst_words=_listed(catalyst_words),
                                       halted=None if halted is None else bool(halted),
                                       halt_codes=_listed(halt_codes))
        self.float_basis, self.group_by = float_basis, group_by
        self.parts = frozenset(self.wanted.parts | ({GROUP_PARTS[group_by]} if group_by in GROUP_PARTS else set()))
        self.left_out: Counter[str] = Counter()
        self.examined = 0

    def _join(self, frame: pd.DataFrame, parts: frozenset[str], count: bool) -> pd.DataFrame:
        columns = [c for part in PART_COLUMNS if part in parts for c in PART_COLUMNS[part]]
        kept = []
        for start in range(0, len(frame), BATCH):
            chunk = frame.iloc[start:start + BATCH]
            pairs = [(str(d)[:10], str(s)) for d, s in zip(chunk["date"], chunk["symbol"], strict=True)]
            facts = day_facts.for_pairs(pairs, self.float_basis, parts)
            rows = [facts[p] for p in pairs]
            if count:
                self.examined += len(rows)
                mask = np.array([day_facts.keep(row, self.wanted, self.left_out) for row in rows], dtype=bool)
            else:
                mask = np.array([day_facts.keep(row, self.wanted) for row in rows], dtype=bool)
            if mask.any():
                passed = [row for row, ok in zip(rows, mask, strict=True) if ok]
                kept.append(chunk[mask].assign(**{c: _typed(c, [r.get(c) for r in passed]) for c in columns}))
        if not kept:
            return frame.iloc[:0].assign(**{c: _typed(c, []) for c in columns})
        return pd.concat(kept, ignore_index=True)

    def join(self, table):
        """The rows of ``table`` (an arrow table or a DataFrame with ``date`` and ``symbol``) that pass the filters,
        with the joined parts' columns, as a DataFrame; ``table`` itself, untouched, when nothing is asked."""
        if not self.parts:
            return table
        return self._join(table.to_pandas() if hasattr(table, "to_pandas") else table, self.parts, True)

    def pool(self, pool: pd.DataFrame, days: Iterable[Any]) -> pd.DataFrame:
        """A control pool held to the filters on ``days`` (the triggers' universe; not counted in ``left_out``);
        ``pool`` itself when no filter is asked (a group alone does not narrow it)."""
        if not self.wanted.parts:
            return pool
        return self._join(pool[pool["date"].isin(set(days))], frozenset(self.wanted.parts), False)

    def left(self) -> dict[str, int]:
        """The stock-days each asked filter left out for an unknown (zero when none); {} when no filter is asked."""
        keys = [key for key, asked in (
            ("catalyst_unknown", "catalyst" in self.wanted.parts),
            ("shares_unknown", self.wanted.float_max is not None and self.wanted.float_unknown == "exclude"),
            ("halts_unknown", "halts" in self.wanted.parts)) if asked]
        return {key: int(self.left_out.get(key, 0)) for key in keys}

    def meta(self, *, left_out: bool = True, control: bool = False) -> dict[str, Any]:
        """What an answer adds when facts were joined (``day_facts``: the filters, parts, rows examined, rules; and
        ``left_out`` unless the answer keeps its own); {} when nothing was joined, so an answer without these
        arguments is unchanged. ``control``: the answer has controls (their pool is held to the filters)."""
        if not self.parts:
            return {}
        asked = {k: v for k, v in day_facts.asked(self.wanted).items() if k != "rvol_daily_min"}
        rules = {"join": JOIN_RULE, **({"float": FLOAT_RULE} if "shares" in self.parts else {}),
                 **({"catalyst": day_facts.CATALYST_RULE} if "catalyst" in self.parts else {}),
                 **({"halts": day_facts.HALT_RULE} if "halts" in self.parts else {}),
                 **({"group": GROUP_RULE} if self.group_by in GROUPS else {}),
                 **({"control": CONTROL_RULE} if control and self.wanted.parts else {})}
        out = {"day_facts": {"filters": {**asked, "float_basis": self.float_basis}, "joined": sorted(self.parts),
                             "examined": self.examined, "rules": rules}}
        return {**out, "left_out": self.left()} if left_out else out


def float_bucket(shares: Any) -> str:
    if shares is None or pd.isna(shares):
        return UNKNOWN
    return FLOAT_LABELS[bisect.bisect_right(FLOAT_EDGES, float(shares))]


def group(frame: pd.DataFrame, group_by: str) -> pd.Series:
    """Each row's group (module docstring) from its joined columns; a stock-day with no value is ``unknown``."""
    if group_by == "float":
        labels = [float_bucket(s) for s in frame["float_shares"]]
    elif group_by == "catalyst":
        labels = [v if isinstance(v, str) else UNKNOWN for v in frame["catalyst_verdict"]]
    else:
        labels = [UNKNOWN if not isinstance(v, str) else c.lower() if isinstance(c, str) else NO_CATEGORY
                  for v, c in zip(frame["catalyst_verdict"], frame["catalyst_category"], strict=True)]
    return pd.Series(labels, index=frame.index, dtype=object)


def order(group_by: str, present: Iterable[str]) -> list[str]:
    """The groups present in summary order: float buckets smallest first; names alphabetical; ``unknown`` last."""
    present = set(present)
    names = FLOAT_LABELS if group_by == "float" else sorted(present - {UNKNOWN})
    return [g for g in (*names, UNKNOWN) if g in present]
