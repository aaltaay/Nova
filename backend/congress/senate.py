"""The Senate eFD's reports (ADR 066): its agreement, its search, then each e-filed report's page.

eFD shows no report before its agreement: ``open_session`` sends the one its page sends (``prohibition_agreement=1``,
the agreement the operator gave on the Congress page) and keeps the session's cookies. ``search`` lists the Periodic
Transaction Reports received between two days; ``read`` reads one e-filed report (``senate_html``). A paper report
is listed, never read. An amendment is dated by the report it corrects (the date in its title).
"""
from __future__ import annotations

import logging
import re
from datetime import date

import requests

from congress import matching, senate_html
from congress.constants_congress import (
    CONGRESS_PARSER_VERSION,
    CONGRESS_SENATE_BASE,
    CONGRESS_SENATE_HOME,
    CONGRESS_SENATE_PAGE,
    CONGRESS_SENATE_PTR_TYPE,
    CONGRESS_SENATE_SEARCH,
)

logger = logging.getLogger(__name__)
PARSER = CONGRESS_PARSER_VERSION["senate"]
CSRF = re.compile(r'name="csrfmiddlewaretoken" value="([^"]+)"')
AMENDMENT_NO = re.compile(r"\(Amendment\s*(\d+)\)", re.I)


class SenateRefused(Exception):
    """eFD did not open its search (its agreement page changed, or it answered with something else)."""


def open_session(net) -> requests.Session:
    s = requests.Session()
    home = net.get(CONGRESS_SENATE_BASE + CONGRESS_SENATE_HOME, session=s)
    home.raise_for_status()
    token = CSRF.search(home.text)
    if not token:
        raise SenateRefused("the agreement page has no form token")
    agreed = net.post(CONGRESS_SENATE_BASE + CONGRESS_SENATE_HOME, session=s,
                      data={"csrfmiddlewaretoken": token.group(1), "prohibition_agreement": "1"},
                      headers={"Referer": CONGRESS_SENATE_BASE + CONGRESS_SENATE_HOME})
    agreed.raise_for_status()
    if not s.cookies.get("csrftoken"):
        raise SenateRefused("the agreement was not accepted (no session token)")
    return s


def _us(d: date) -> str:
    return d.strftime("%m/%d/%Y")


def search(net, session: requests.Session, start: date, end: date) -> list[senate_html.SenateReport]:
    """Every PTR eFD received from ``start`` to ``end``, in eFD's order."""
    out: list[senate_html.SenateReport] = []
    offset, total = 0, None
    while total is None or offset < total:
        resp = net.post(CONGRESS_SENATE_BASE + CONGRESS_SENATE_SEARCH, session=session,
                        headers={"X-CSRFToken": session.cookies.get("csrftoken") or "",
                                 "Referer": CONGRESS_SENATE_BASE + "/search/"},
                        data={"start": str(offset), "length": str(CONGRESS_SENATE_PAGE),
                              "report_types": CONGRESS_SENATE_PTR_TYPE, "filer_types": "[]",
                              "submitted_start_date": f"{_us(start)} 00:00:00",
                              "submitted_end_date": f"{_us(end)} 23:59:59", "candidate_state": "",
                              "senator_state": "", "office_id": "", "first_name": "", "last_name": ""})
        resp.raise_for_status()
        try:
            body = resp.json()
        except ValueError as exc:
            raise SenateRefused("the search did not answer in JSON (the session ended)") from exc
        total = int(body.get("recordsTotal") or 0)
        page = body.get("data") or []
        for row in page:
            report = senate_html.search_row(row, CONGRESS_SENATE_BASE)
            if report is None:
                logger.warning("congress: a Senate search row had an unknown shape: %r", row[:4] if isinstance(row, list) else row)
            else:
                out.append(report)
        if not page:
            break
        offset += CONGRESS_SENATE_PAGE
    return out


def record(r: senate_html.SenateReport, members: list[dict]) -> dict:
    """A report record for one search row (not yet read)."""
    return {"id": r.id, "chamber": "senate", "filer_name": r.filer, "filer_first": r.first, "filer_last": r.last,
            "filer_state": None, "filer_district": None, "bioguide": matching.senate(members, r.first, r.last),
            "filed": r.filed, "kind": r.kind, "url": r.url, "title": r.title,
            "amends": r.report_date if r.amendment else None, "amended_by": None, "parser": None, "read_at": None,
            "error": None, "trades": 0}


def reconcile(reports: dict[str, dict]) -> dict[str, str | None]:
    """Which report stands for each corrected one, over every kept Senate report (whatever order they were found in).

    A report and its amendments share the filer and the corrected report's date; the newest amendment (by its number,
    then the day eFD received it) stands and every other one of them -- the original and older amendments -- is
    ``amended_by`` it. Answers only the reports whose ``amended_by`` must change."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in reports.values():
        date = r.get("amends") or _title_date(r)
        if r["chamber"] == "senate" and date:
            groups.setdefault((r.get("filer_name") or "", date), []).append(r)
    out: dict[str, str | None] = {}
    for group in groups.values():
        amendments = [r for r in group if r.get("amends")]
        if not amendments:
            continue
        standing = max(amendments, key=lambda r: (_amendment_no(r), r["filed"], r["id"]))
        for r in group:
            want = None if r["id"] == standing["id"] else standing["id"]
            if r.get("amended_by") != want:
                out[r["id"]] = want
    return out


def _amendment_no(report: dict) -> int:
    m = AMENDMENT_NO.search(report.get("title") or "")
    return int(m.group(1)) if m else 1


def _title_date(report: dict) -> str | None:
    m = senate_html.TITLE_DATE.search(report.get("title") or "")
    if not m:
        return None
    mm, dd, yyyy = m.group(1).split("/")
    return f"{yyyy}-{mm}-{dd}"


def pending(report: dict) -> bool:
    return report["chamber"] == "senate" and report["kind"] == "electronic" and report.get("parser") != PARSER


def read(net, session: requests.Session, report: dict, now: float) -> tuple[dict, list[dict] | None]:
    """Read one e-filed report: (the updated record, its rows or None when eFD did not answer with it)."""
    resp = net.get(report["url"], session=session)
    if resp.status_code != 200:
        return {**report, "error": f"eFD answered HTTP {resp.status_code}"}, None
    rows = senate_html.parse_report(resp.text)
    if rows is None:
        if CSRF.search(resp.text):
            raise SenateRefused("eFD sent its agreement page again (the session ended)")
        return {**report, "parser": PARSER, "read_at": now, "error": "the report page has no transaction table"}, []
    return ({**report, "parser": PARSER, "read_at": now, "error": None},
            [{"tx": r.tx_date, "notified": None, "owner": r.owner, "ticker": r.ticker, "asset": r.asset,
              "asset_type": r.asset_type, "tx_type": r.tx_type, "amount": r.amount, "status": None,
              "subholding": None, "description": r.comment} for r in rows])
