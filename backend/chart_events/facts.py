"""A registrant's tagged figures, from SEC's companyfacts file. Pure.

Every fact carries its filing's accession (``accn``), form, filing date (``filed``), the filing's fiscal year
and period (``fy`` / ``fp``), and its own ``start`` / ``end``. A report's figure is its own fact for its
current period (``_period``: the quarter for a 10-Q, not its year to date; the year for an annual report);
a release that no report claims takes the first filing that tagged its period (``value_for_period``), and
says which. Revenue is total revenue (``Revenues``) before revenue from contracts with customers, which
leaves out lease, interest and other revenue (``CHART_EVENTS_REVENUE_CONCEPTS``). A figure nobody tagged is
None, never estimated.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Mapping

from chart_events.constants_chart_events import (
    CHART_EVENTS_ANNUAL_FORMS,
    CHART_EVENTS_EPS_CONCEPTS,
    CHART_EVENTS_EPS_UNIT,
    CHART_EVENTS_MIN_PERIOD_DAYS,
    CHART_EVENTS_MONEY_UNIT,
    CHART_EVENTS_NET_INCOME_CONCEPTS,
    CHART_EVENTS_REVENUE_CONCEPTS,
)

DAYS_PER_MONTH = 30.44
# A 52-53 week fiscal year (and its quarters) ends within days of its nominal date.
YEAR_END_SLACK_DAYS = 7
CONCEPTS = {
    "revenue": (CHART_EVENTS_REVENUE_CONCEPTS, CHART_EVENTS_MONEY_UNIT),
    "net_income": (CHART_EVENTS_NET_INCOME_CONCEPTS, CHART_EVENTS_MONEY_UNIT),
    "eps": (CHART_EVENTS_EPS_CONCEPTS, CHART_EVENTS_EPS_UNIT),
}
# One concept group's facts by accession: the unit read and that accession's duration facts in it.
Group = dict[str, tuple[str, list[dict]]]
Span = tuple[date, date]


def as_day(raw: Any) -> date | None:
    try:
        return date.fromisoformat(str(raw)[:10])
    except (TypeError, ValueError):
        return None


def months_of(span: Span) -> int:
    return round((span[1] - span[0]).days / DAYS_PER_MONTH)


def near(a: date | None, b: date | None) -> bool:
    return a is not None and b is not None and abs((a - b).days) <= YEAR_END_SLACK_DAYS


def _span(fact: Mapping[str, Any]) -> Span | None:
    start, end = as_day(fact.get("start")), as_day(fact.get("end"))
    if start is None or end is None or (end - start).days < CHART_EVENTS_MIN_PERIOD_DAYS:
        return None
    return start, end


def _units(tags: Mapping[str, Any], taxonomy: str, concept: str, unit: str) -> list[tuple[str, list]]:
    """A concept's units, ``unit`` first."""
    units = (((tags.get(taxonomy) or {}).get(concept)) or {}).get("units") or {}
    return sorted(units.items(), key=lambda kv: kv[0] != unit)


def concept_group(facts: Mapping[str, Any] | None, concepts: tuple[tuple[str, str], ...], unit: str) -> Group:
    """Each accession's duration facts for the first concept (in ``concepts`` order) that tags it, in
    ``unit`` when the report used it, else in the first unit it used."""
    tags = ((facts or {}).get("facts")) or {}
    out: Group = {}
    for taxonomy, concept in concepts:
        found: Group = {}
        for name, rows in _units(tags, taxonomy, concept, unit):
            for fact in rows or []:
                accn = fact.get("accn")
                if not accn or accn in out or _span(fact) is None:
                    continue
                held = found.setdefault(accn, (name, []))
                if held[0] == name:
                    held[1].append(fact)
        out.update(found)
    return out


def current_period(rows: list[dict], form: str, report_end: date | None) -> Span:
    """The report's current period among its facts: those ending at the report's period end (else the
    latest end), the longest for an annual report, the shortest otherwise (a 10-Q's quarter, not its
    year to date)."""
    spans = sorted({s for s in (_span(f) for f in rows) if s is not None})
    ends = {end for _, end in spans}
    end = report_end if report_end in ends else max(ends)
    at_end = [s for s in spans if s[1] == end]
    pick = max if form in CHART_EVENTS_ANNUAL_FORMS else min
    return pick(at_end, key=lambda s: (s[1] - s[0]).days)


def _figure(fact: Mapping[str, Any], unit: str) -> dict[str, Any]:
    return {"value": float(fact["val"]), "unit": unit, "form": fact.get("form"), "filed": fact.get("filed"),
            "period_end": fact.get("end")}


def own_value(group: Group, accn: str, span: Span) -> dict[str, Any] | None:
    hit = group.get(accn)
    if not hit:
        return None
    unit, rows = hit
    fact = next((f for f in rows if _span(f) == span and isinstance(f.get("val"), (int, float))), None)
    return _figure(fact, unit) if fact else None


def value_for_period(facts: Mapping[str, Any] | None, concepts: tuple[tuple[str, str], ...], unit: str,
                     end: date, months: int) -> dict[str, Any] | None:
    """The first filing that tagged a figure for the period of ``months`` ending ``end`` -- first concept
    that has one, ``unit`` first -- for a release no report claims."""
    tags = ((facts or {}).get("facts")) or {}
    for taxonomy, concept in concepts:
        for name, rows in _units(tags, taxonomy, concept, unit):
            hits = []
            for fact in rows or []:
                span = _span(fact)
                if (span and near(span[1], end) and months_of(span) == months and fact.get("filed")
                        and isinstance(fact.get("val"), (int, float))):
                    hits.append(fact)
            if hits:
                return _figure(min(hits, key=lambda f: f["filed"]), name)
    return None
