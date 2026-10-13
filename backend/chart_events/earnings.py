"""Earnings events from a registrant's SEC EDGAR filings. Pure.

Two files from EDGAR, and the releases ``release_text.py`` read (figures: ``facts.py``; fiscal
period names: ``fiscal.py``):

  submissions   ``data.sec.gov/submissions/CIK##########.json``: the ``filings.recent`` columns
                ``accessionNumber``, ``form``, ``filingDate``, ``reportDate``, ``items`` and ``primaryDocument``
                (a year of filings or 1,000, whichever is more), and ``fiscalYearEnd`` ("0630")
  companyfacts  ``data.sec.gov/api/xbrl/companyfacts/CIK##########.json``: every fact the registrant tagged,
                each with its filing's accession (``accn``), form, filing date (``filed``), fiscal year and
                period (``fy`` / ``fp``) and its own ``start`` / ``end``

A **report** is a periodic report of results -- 10-Q, 10-K, 20-F, 40-F -- or a 6-K whose accession carries
financial facts (a foreign issuer's interim report in XBRL). An amendment is never a report, and two reports
of one period are one (the first filed): companyfacts writes a 20-F/A as ``20-F``. A **release** is an 8-K
whose items include 2.02 ("Results of Operations and Financial Condition") that its words do not show to be
something else -- deliveries, a restatement, an offering (``release_text.read_8k``) -- or a 6-K whose words
report results (``release_text.read_6k``). It came out on the day the company says ("On August 12, 2025,
..."), else the 8-K's date of event, when either is within ``CHART_EVENTS_RELEASE_STATED_DAYS`` before the
filing; else on its filing day.

A release is **strong** when its words say results, **weak** when they were not read or say only that a
press release is attached (an Item 2.02 8-K only: TSLA's deliveries, PLUG's asset sale, SNAP's layoffs read
so), **preliminary** when they say preliminary results. An event is one report, marked on the day its results
came out: in the window from its period's end to ``CHART_EVENTS_RELEASE_AFTER_REPORT_DAYS`` after the report,
the strongest kind of release there is -- of those by the report's filing, the last one, or the first of a
cluster within ``CHART_EVENTS_RELEASE_CLUSTER_DAYS`` of it (XPEV's press release, then its Hong Kong results
a day later); else the first one after the report -- and never later than the report itself. The last one,
since what comes earlier in a quarter is what is not the results: deliveries (TSLA on the 2nd), a
preliminary, a date to come, an acquisition with "certain financial results" (LUNR); a restatement after
the results is not a release at all (Item 4.02, BBAI 2025-03-18). Every other release in the window is
listed on the event (``other_releases``), never marked. A strong release no report claims yet is an event
of its own: a 6-K's period comes from its words, an 8-K's is unknown -- unless it publishes the interim or
annual report of a period a mark already stands for, when it is listed there instead (XPEV's Hong Kong
interim report a month after its second-quarter results). Revenue, net income and basic EPS are the report's own facts for its current period (the
quarter for a 10-Q, the year for an annual report, the period a 6-K covers); for a release no report claims,
the first filing that tagged that period, which the figure names. A figure nobody tagged is null, never
estimated.

Only the day is kept, SEC's ``filingDate``. The submissions file's ``acceptanceDateTime`` is not a time to
read: against each filing's index page it is true UTC for some filers (NIO's 20-F accepted 2026-04-10
07:54:42 ET reads ``11:54:42Z``) and the Eastern time pushed through the offset twice for others (Apple's
8-K accepted 2026-07-30 16:30:28 ET reads ``2026-07-31T00:30:28Z``), so whether results came before the
open or after the close is not said.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Mapping

from chart_events.constants_chart_events import (
    CHART_EVENTS_INTERIM_FORMS,
    CHART_EVENTS_PERIODIC_FORMS,
    CHART_EVENTS_RELEASE_AFTER_REPORT_DAYS,
    CHART_EVENTS_RELEASE_CLUSTER_DAYS,
    CHART_EVENTS_RELEASE_FORM,
    CHART_EVENTS_RELEASE_ITEM,
    CHART_EVENTS_RELEASE_STATED_DAYS,
    CHART_EVENTS_SOURCE_SEC,
)
from chart_events.facts import CONCEPTS, Group, concept_group, value_for_period
from chart_events.facts import as_day as _day
from chart_events.facts import current_period as _period
from chart_events.facts import months_of as _months
from chart_events.facts import near as _near
from chart_events.facts import own_value as _own_value
from chart_events.fiscal import fiscal_label, fiscal_year_end, period_label, quarter_end
from chart_events.fiscal import naming_offset as _naming_offset

_COLUMNS = ("accessionNumber", "form", "filingDate", "reportDate", "items", "primaryDocument")
# A filing that publishes the interim or annual report of a period whose results are already out (XPEV's Hong
# Kong "Interim Report" a month after its Q2 results). Only such a filing is folded into the period's mark: any
# other later release keeps its own, so an earlier false mark never hides the real one (NNOX 2026: an
# offering's caveat on "preliminary estimates" in August, its Q2 results on September 9).
_REPORT_PUBLISHED = re.compile(r"\b(?:interim|annual) report\b", re.I)


def _block(block: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    cols = {k: (block or {}).get(k) or [] for k in _COLUMNS}
    count = len(cols["accessionNumber"])
    return [{k: (cols[k][i] if i < len(cols[k]) else None) for k in _COLUMNS} for i in range(count)]


def filings(submissions: Mapping[str, Any] | None,
            pages: Mapping[str, Mapping[str, Any]] | None = None) -> list[dict[str, Any]]:
    """The ``filings.recent`` columns, and those of each older page read, as one dict per filing."""
    rows = _block((((submissions or {}).get("filings") or {}).get("recent")) or {})
    for page in (pages or {}).values():
        rows += _block(page)
    return rows


def older_pages(submissions: Mapping[str, Any] | None, since: date) -> list[tuple[str, date]]:
    """The older pages of filings EDGAR lists beside ``recent`` that reach ``since``: (file name, last
    filing date), newest first. A page that cannot be dated is listed as reaching it."""
    listed = (((submissions or {}).get("filings") or {}).get("files")) or []
    out = []
    for entry in listed if isinstance(listed, list) else []:
        to = _day((entry or {}).get("filingTo")) or date.max
        if to >= since:
            out.append((str((entry or {}).get("name") or ""), to))
    return sorted(out, key=lambda p: p[1], reverse=True)


def _items(row: Mapping[str, Any]) -> set[str]:
    return {s.strip() for s in str(row.get("items") or "").split(",")}


def is_release_8k(row: Mapping[str, Any]) -> bool:
    return row.get("form") == CHART_EVENTS_RELEASE_FORM and CHART_EVENTS_RELEASE_ITEM in _items(row)


def release_filings(rows: list[dict[str, Any]], since: date) -> list[dict[str, Any]]:
    """The 6-Ks and Item 2.02 8-Ks filed from ``since`` on, newest first: the ones whose words are read."""
    found = [r for r in rows if (r.get("form") in CHART_EVENTS_INTERIM_FORMS or is_release_8k(r))
             and r.get("accessionNumber") and r.get("primaryDocument")
             and (_day(r.get("filingDate")) or date.min) >= since]
    return sorted(found, key=lambda r: str(r.get("filingDate")), reverse=True)


_STRENGTH = {"strong": 2, "weak": 1, "preliminary": 0}


def _rank(rel: Mapping[str, Any]) -> tuple[int, bool, bool, bool]:
    said = rel["said"] or {}
    return _STRENGTH[rel["strength"]], rel["read"], bool(said.get("named")), bool(said.get("end"))


def _strength(row: Mapping[str, Any], reading: Mapping[str, Any] | None) -> str | None:
    """How a filing counts as a release (``strong`` / ``weak`` / ``preliminary``), or None for no release."""
    kind = (reading or {}).get("kind")
    if is_release_8k(row):
        if kind == "other":
            return None
        return {"results": "strong", "preliminary": "preliminary"}.get(kind, "weak")
    if row.get("form") in CHART_EVENTS_INTERIM_FORMS and kind in ("results", "preliminary"):
        return "strong" if kind == "results" else "preliminary"
    return None


def _release_day(filed: date, *said_days: Any) -> date:
    """The day a release came out: the first of the days it gives (the company's own, then the 8-K's date of
    event) that is on or up to ``CHART_EVENTS_RELEASE_STATED_DAYS`` before its filing; else its filing day."""
    for raw in said_days:
        day = _day(raw)
        if day is not None and 0 <= (filed - day).days <= CHART_EVENTS_RELEASE_STATED_DAYS:
            return day
    return filed


def _releases(rows: list[dict], readings: Mapping[str, Any], fye: tuple[int, int] | None,
              offset: int) -> list[dict[str, Any]]:
    """Item 2.02 8-Ks that are not something else and 6-Ks that report results, one a day: the stronger
    release, one whose words were read, one that names its quarter in the company's words (NIO's press
    release over its Hong Kong interim report the same day), then one that names its period's end. A named
    quarter without an end gets its nominal end (``end_nominal``)."""
    by_day: dict[date, dict[str, Any]] = {}
    for row in rows:
        accn, form, filed = row.get("accessionNumber"), row.get("form"), _day(row.get("filingDate"))
        reading = readings.get(accn) if accn else None
        strength = _strength(row, reading) if accn and filed else None
        if strength is None:
            continue
        said = dict(reading) if reading else {}
        nominal = quarter_end(said["named"], fye, offset) if said.get("named") else None
        if said.get("named") and not _near(_day(said.get("end")), nominal):
            said.update(end=nominal.isoformat() if nominal else None, months=3, end_nominal=True)
        day = _release_day(filed, said.get("stated"), row.get("reportDate") if is_release_8k(row) else None)
        rel = {"accn": accn, "form": form, "day": day, "filed": filed, "said": said or None,
               "read": reading is not None, "strength": strength}
        held = by_day.get(day)
        if held is None or _rank(rel) > _rank(held):
            by_day[day] = rel
    return sorted(by_day.values(), key=lambda r: (r["day"], r["accn"]))


def _reports(rows: list[dict], groups: list[Group]) -> list[dict[str, Any]]:
    """Every report of results, the first filed of each period."""
    forms = {r["accessionNumber"]: r.get("form") for r in rows if r.get("accessionNumber")}
    tagged: dict[str, list[dict]] = {}
    for group in groups:
        for accn, (_unit, facts) in group.items():
            tagged.setdefault(accn, facts)
    found: dict[str, dict[str, Any]] = {}
    for row in rows:
        accn, form, day = row.get("accessionNumber"), row.get("form"), _day(row.get("filingDate"))
        periodic = form in CHART_EVENTS_PERIODIC_FORMS or (form in CHART_EVENTS_INTERIM_FORMS and accn in tagged)
        if accn and day and periodic:
            found[accn] = {"accn": accn, "form": form, "day": day, "end": _day(row.get("reportDate"))}
    for accn, facts in tagged.items():
        form, day = facts[0].get("form"), _day(facts[0].get("filed"))
        listed = forms.get(accn)
        # A filing the submissions file lists under a form that is no report (a 20-F/A) is not one.
        if accn in found or (listed is not None and listed not in CHART_EVENTS_PERIODIC_FORMS
                             and listed not in CHART_EVENTS_INTERIM_FORMS):
            continue
        if day and (form in CHART_EVENTS_PERIODIC_FORMS or form in CHART_EVENTS_INTERIM_FORMS):
            found[accn] = {"accn": accn, "form": form, "day": day, "end": None}
    first: dict[tuple, dict[str, Any]] = {}
    for rep in sorted(found.values(), key=lambda r: (r["day"], r["accn"])):
        rep["facts"] = tagged.get(rep["accn"]) or []
        rep["period"] = _period(rep["facts"], rep["form"], rep["end"]) if rep["facts"] else None
        rep["end"] = rep["end"] or (rep["period"][1] if rep["period"] else None)
        key = (rep["period"][1], _months(rep["period"])) if rep["period"] else ("untagged", rep["accn"])
        first.setdefault(key, rep)
    return sorted(first.values(), key=lambda r: (r["day"], r["accn"]))


def _claim(rep: dict[str, Any], releases: list[dict[str, Any]], claimed: set[str]) -> tuple[dict | None, list]:
    """The release that brought ``rep``'s results out, and every other release in its window."""
    end = rep["end"]
    if end is None:
        return None, []
    last = rep["day"] + timedelta(days=CHART_EVENTS_RELEASE_AFTER_REPORT_DAYS)
    window = [r for r in releases if r["accn"] not in claimed and end < r["day"] <= last
              and not ((r["said"] or {}).get("end") and not _near(_day(r["said"]["end"]), end))]
    chosen = None
    for strength in ("strong", "weak"):
        found = [r for r in window if r["strength"] == strength]
        before = [r for r in found if r["day"] <= rep["day"]]
        if before:
            chosen = before[-1]
            for r in reversed(before[:-1]):
                if (chosen["day"] - r["day"]).days > CHART_EVENTS_RELEASE_CLUSTER_DAYS:
                    break
                chosen = r
        elif found:
            chosen = found[0]
        if chosen is not None:
            break
    claimed.update(r["accn"] for r in window)
    return chosen, [r for r in window if r is not chosen]


def _stamp(item: Mapping[str, Any]) -> dict[str, Any]:
    """A filing on the wire: its form and accession, the day it counts for, and the day SEC dated it."""
    filed = item.get("filed") or item["day"]
    return {"form": item["form"], "accession": item["accn"], "day": item["day"].isoformat(),
            "filed": filed.isoformat()}


def _event(accn: str, day: date, *, release: dict | None, report: dict | None, others: list,
           fiscal: tuple[Any, Any, str | None], span: tuple[date | None, date | None, int | None],
           figures: dict[str, Any], pending: bool) -> dict[str, Any]:
    fy, fp, label = fiscal
    start, end, months = span
    return {
        "id": f"earnings:{accn}",
        "kind": "earnings",
        "day": day.isoformat(),
        "release": _stamp(release) if release else None,
        "other_releases": [_stamp(r) for r in others],
        "report": _stamp(report) if report else None,
        "report_pending": pending,
        "said": ((release or {}).get("said") or {}).get("said"),
        "fiscal_year": fy,
        "fiscal_period": fp,
        "period_label": label,
        "period_start": start.isoformat() if start else None,
        "period_end": end.isoformat() if end else None,
        "period_months": months,
        **figures,
        "source": CHART_EVENTS_SOURCE_SEC,
    }


def events(submissions: Mapping[str, Any] | None, facts: Mapping[str, Any] | None, *,
           pages: Mapping[str, Mapping[str, Any]] | None = None, readings: Mapping[str, Any] | None = None,
           since: date | None = None, releases_known_since: date | None = None) -> list[dict[str, Any]]:
    """The registrant's earnings events, oldest first (from ``since`` on, when given).

    ``pages`` are the older pages of filings read; ``readings`` holds what ``release_text`` read of each 6-K
    and Item 2.02 8-K whose words were read (None for a 6-K that is not results). ``releases_known_since`` is
    the first day every release is known from -- the oldest filing read, or for a registrant that files 6-Ks
    the first day its 6-Ks were read: a report whose period ended before it is left out, since its results
    may have come out on a release that was not read, and a mark on its filing day could sit weeks late."""
    rows = filings(submissions, pages)
    groups = {name: concept_group(facts, c, unit) for name, (c, unit) in CONCEPTS.items()}
    reports = _reports(rows, list(groups.values()))
    fye = fiscal_year_end(submissions)
    offset = _naming_offset(reports, fye)
    releases = _releases(rows, readings or {}, fye, offset)
    if releases_known_since is not None:
        reports = [r for r in reports if r["end"] is not None and r["end"] >= releases_known_since]
        releases = [r for r in releases if r["day"] >= releases_known_since]
    claimed: set[str] = set()
    out: list[dict[str, Any]] = []
    for rep in reports:
        release, others = _claim(rep, releases, claimed)
        period, first = rep["period"], (rep["facts"][0] if rep["facts"] else {})
        months = _months(period) if period else None
        out.append(_event(
            rep["accn"], min(release["day"], rep["day"]) if release else rep["day"],
            release=release, report=rep, others=others,
            fiscal=(first.get("fy"), first.get("fp"), period_label(first.get("fy"), first.get("fp"), months)),
            span=(period[0] if period else None, rep["end"], months),
            figures={name: (_own_value(groups[name], rep["accn"], period) if period else None) for name in CONCEPTS},
            pending=False))
    newest_report = max((r["day"] for r in reports), default=None)
    marked = [(_day(e["period_end"]), e) for e in out if e["period_end"]]
    for rel in releases:
        if rel["accn"] in claimed or rel["strength"] != "strong":
            continue
        said = rel["said"] or {}
        end, months = _day(said.get("end")), said.get("months")
        republished = bool(_REPORT_PUBLISHED.search(said.get("said") or ""))
        before = next((e for at, e in marked if _near(at, end) and e["day"] <= rel["day"].isoformat()), None)
        if before is not None and republished:
            before["other_releases"].append(_stamp(rel))
            continue
        label = said.get("named") or (fiscal_label(end, months, fye, offset) if end and months else None)
        figures = {name: (value_for_period(facts, c, unit, end, months) if end and months else None)
                   for name, (c, unit) in CONCEPTS.items()}
        tagged_end = next((_day(f["period_end"]) for f in figures.values() if f), None)
        # A nominal quarter end (from the named quarter) is shown only once a tagged figure confirms it.
        shown_end = tagged_end or (None if said.get("end_nominal") else end)
        out.append(_event(
            rel["accn"], rel["day"], release=rel, report=None, others=[], fiscal=(None, None, label),
            span=(None, shown_end, months), figures=figures,
            pending=newest_report is None or rel["day"] > newest_report))
        if end is not None:
            marked.append((end, out[-1]))
    out.sort(key=lambda e: (e["day"], e["id"]))
    return [e for e in out if since is None or e["day"] >= since.isoformat()]
