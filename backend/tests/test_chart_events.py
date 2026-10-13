"""Earnings and split marks on the daily charts (``backend/chart_events``, operator ask 2026-10-12).

The cases are the filings read while building it: Apple's 8-K Item 2.02 the day before each 10-Q, MNDR's
first-half results on a 6-K with no financial facts (Webull: 03/12/2026, "2026 H1", revenue 3.95M USD) and a
20-F/A that companyfacts calls a 20-F, NIO's quarterly results 6-Ks beside its XBRL interim report, and the
Item 2.02 8-Ks that are not earnings (LCID's deliveries, BBAI's restatement, LUNR's acquisition, ASTS's
offering, TSLA's deliveries, XPEV's monthly delivery results, NIO's profit alert, SNDL's date to come) -- each
found by comparing the marks with Yahoo's earnings dates on 49 stocks (2026-10-12).
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from chart_events import earnings, fiscal, release_text, routes, splits
from chart_events.reader import ChartEventsReader
from sim.session_clock import ET


def _subs(rows: list[tuple], fye: str = "1231", files: list | None = None) -> dict:
    """A submissions file: rows of (accession, form, filingDate, reportDate, items, primaryDocument)."""
    keys = ("accessionNumber", "form", "filingDate", "reportDate", "items", "primaryDocument")
    recent = {k: [r[i] if i < len(r) else "" for r in rows] for i, k in enumerate(keys)}
    return {"name": "Test Co", "fiscalYearEnd": fye, "filings": {"recent": recent, "files": files or []}}


def _fact(accn, form, filed, start, end, val, fy=None, fp=None):
    return {"accn": accn, "form": form, "filed": filed, "start": start, "end": end, "val": val, "fy": fy, "fp": fp}


def _facts(**concepts) -> dict:
    """``revenue=[...]`` style: concept name -> facts, unit USD (or USD/shares for EPS)."""
    tags: dict = {"us-gaap": {}}
    for name, rows in concepts.items():
        unit = "USD/shares" if name.startswith("EarningsPerShare") else "USD"
        tags["us-gaap"][name] = {"units": {unit: rows}}
    return {"facts": tags}


# -- earnings ------------------------------------------------------------------------------------------------


def test_us_filer_marks_the_8k_release_and_reads_the_quarter_not_the_year_to_date():
    subs = _subs([
        ("A-10Q", "10-Q", "2026-07-31", "2026-06-27", "", "q.htm"),
        ("A-8K", "8-K", "2026-07-30", "2026-07-30", "2.02,9.01", "k.htm"),
    ])
    facts = _facts(
        RevenueFromContractWithCustomerExcludingAssessedTax=[
            _fact("A-10Q", "10-Q", "2026-07-31", "2025-09-28", "2026-06-27", 364_357e6, 2026, "Q3"),
            _fact("A-10Q", "10-Q", "2026-07-31", "2026-03-29", "2026-06-27", 109_417e6, 2026, "Q3"),
        ],
        EarningsPerShareBasic=[_fact("A-10Q", "10-Q", "2026-07-31", "2026-03-29", "2026-06-27", 2.03, 2026, "Q3")],
    )
    [ev] = earnings.events(subs, facts)
    assert ev["day"] == "2026-07-30"
    assert ev["release"]["form"] == "8-K" and ev["report"]["form"] == "10-Q"
    assert ev["period_label"] == "2026 Q3" and ev["period_months"] == 3
    assert ev["revenue"]["value"] == 109_417e6 and ev["eps"]["value"] == 2.03
    assert ev["report_pending"] is False


def test_total_revenue_wins_over_revenue_from_contracts():
    subs = _subs([("R-10Q", "10-Q", "2026-05-10", "2026-03-31")])
    facts = _facts(
        RevenueFromContractWithCustomerExcludingAssessedTax=[
            _fact("R-10Q", "10-Q", "2026-05-10", "2026-01-01", "2026-03-31", 90.0, 2026, "Q1")],
        Revenues=[_fact("R-10Q", "10-Q", "2026-05-10", "2026-01-01", "2026-03-31", 100.0, 2026, "Q1")],
    )
    assert earnings.events(subs, facts)[0]["revenue"]["value"] == 100.0


def test_annual_report_reads_the_year_and_an_amendment_is_no_second_mark():
    subs = _subs([
        ("K-20FA", "20-F/A", "2026-04-09", "2025-06-30"),
        ("K-20F", "20-F", "2025-10-31", "2025-06-30"),
    ], fye="0630")
    facts = _facts(RevenueFromContractWithCustomerExcludingAssessedTax=[
        # companyfacts writes the amendment's form as "20-F"
        _fact("K-20FA", "20-F", "2026-04-09", "2024-07-01", "2025-06-30", 7_646_739, 2025, "FY"),
        _fact("K-20F", "20-F", "2025-10-31", "2024-07-01", "2025-06-30", 7_646_739, 2025, "FY"),
        _fact("K-20F", "20-F", "2025-10-31", "2025-04-01", "2025-06-30", 1_900_000, 2025, "FY"),
    ])
    [ev] = earnings.events(subs, facts)
    assert ev["day"] == "2025-10-31" and ev["period_label"] == "2025 FY" and ev["period_months"] == 12
    assert ev["revenue"]["value"] == 7_646_739


def test_a_release_with_no_report_yet_says_so_and_has_no_figures():
    subs = _subs([
        ("N-8K", "8-K", "2026-10-08", "2026-10-08", "2.02"),
        ("O-10Q", "10-Q", "2026-08-12", "2026-06-30"),
    ])
    facts = _facts(Revenues=[_fact("O-10Q", "10-Q", "2026-08-12", "2026-04-01", "2026-06-30", 5.0, 2026, "Q2")])
    assert [e["day"] for e in earnings.events(subs, facts)] == ["2026-08-12"]     # unread: no mark of its own
    out = earnings.events(subs, facts, readings={"N-8K": _read("results")})
    pending = out[-1]
    assert pending["day"] == "2026-10-08" and pending["report"] is None and pending["report_pending"] is True
    assert pending["revenue"] is None and pending["period_label"] is None


def test_unread_releases_mark_the_last_one_before_the_report():
    # An older year whose 8-Ks were not read: a deliveries or preliminary 8-K comes before the earnings one.
    subs = _subs([
        ("P-10K", "10-K", "2026-03-02", "2025-12-31"),
        ("P-final", "8-K", "2026-02-25", "2026-02-25", "2.02,9.01"),
        ("P-prelim", "8-K", "2026-01-12", "2026-01-12", "2.02,7.01"),
    ])
    facts = _facts(Revenues=[_fact("P-10K", "10-K", "2026-03-02", "2025-01-01", "2025-12-31", 9.0, 2025, "FY")])
    [ev] = earnings.events(subs, facts)
    assert ev["day"] == "2026-02-25"
    assert [r["day"] for r in ev["other_releases"]] == ["2026-01-12"]


def test_results_beat_an_8k_that_only_attaches_a_press_release():
    # TSLA: deliveries on the 2nd ("published the press release ... attached"), results on the 22nd.
    subs = _subs([
        ("T-10Q", "10-Q", "2026-07-23", "2026-06-30"),
        ("T-results", "8-K", "2026-07-22", "2026-07-22", "2.02,9.01"),
        ("T-deliveries", "8-K", "2026-07-02", "2026-07-02", "2.02,9.01"),
    ])
    facts = _facts(Revenues=[_fact("T-10Q", "10-Q", "2026-07-23", "2026-04-01", "2026-06-30", 1.0, 2026, "Q2")])
    readings = {"T-results": _read("results"), "T-deliveries": _read("unknown")}
    [ev] = earnings.events(subs, facts, readings=readings)
    assert ev["day"] == "2026-07-22" and [r["day"] for r in ev["other_releases"]] == ["2026-07-02"]
    # Read or not, a deliveries 8-K before the results never wins: the last release does.
    [unread] = earnings.events(subs, facts)
    assert unread["day"] == "2026-07-22"


def _read(kind, **more):
    return {"kind": kind, "said": None, "months": None, "end": None, "named": None, "stated": None, **more}


def test_the_results_release_is_marked_and_never_a_restatement():
    # BBAI: results 2025-03-06 (Items 2.02, 8.01), then a restatement 03-18 (Items 2.02, 4.02); 10-K 03-31.
    subs = _subs([
        ("B-10K", "10-K", "2025-03-31", "2024-12-31"),
        ("B-restate", "8-K", "2025-03-18", "2025-03-17", "2.02,4.02"),
        ("B-results", "8-K", "2025-03-06", "2025-03-06", "2.02,8.01"),
    ])
    facts = _facts(Revenues=[_fact("B-10K", "10-K", "2025-03-31", "2024-01-01", "2024-12-31", 1.0, 2024, "FY")])
    readings = {"B-restate": _read("other"), "B-results": _read("results")}
    [ev] = earnings.events(subs, facts, readings=readings)
    assert ev["day"] == "2025-03-06" and ev["release"]["accession"] == "B-results"
    assert ev["other_releases"] == []


def test_a_preliminary_release_is_listed_and_the_report_marks_the_results():
    # LUNR: "certain financial results" with an acquisition 2025-11-04; the quarter's results with the 10-Q.
    subs = _subs([
        ("L-10Q", "10-Q", "2025-11-13", "2025-09-30"),
        ("L-8K", "8-K", "2025-11-04", "2025-11-03", "1.01,2.02,3.02,7.01,9.01"),
    ])
    facts = _facts(Revenues=[_fact("L-10Q", "10-Q", "2025-11-13", "2025-07-01", "2025-09-30", 1.0, 2025, "Q3")])
    [ev] = earnings.events(subs, facts, readings={"L-8K": _read("preliminary")})
    assert ev["day"] == "2025-11-13" and ev["release"] is None
    assert [r["accession"] for r in ev["other_releases"]] == ["L-8K"]


def test_two_results_6ks_days_apart_mark_the_first():
    subs = _subs([
        ("X-20F", "20-F", "2026-04-20", "2025-12-31"),
        ("X-hk", "6-K", "2026-03-18", "2026-03-18", "", "hk.htm"),
        ("X-pr", "6-K", "2026-03-17", "2026-03-17", "", "pr.htm"),
    ])
    facts = _facts(Revenues=[_fact("X-20F", "20-F", "2026-04-20", "2025-01-01", "2025-12-31", 1.0, 2025, "FY")])
    readings = {"X-hk": _read("results"), "X-pr": _read("results")}
    [ev] = earnings.events(subs, facts, readings=readings)
    assert ev["day"] == "2026-03-17" and [r["accession"] for r in ev["other_releases"]] == ["X-hk"]


def test_a_release_counts_from_the_day_the_company_gives():
    # An 8-K filed the morning after an evening release: its date of event; a 6-K: its own "On <date>".
    subs = _subs([
        ("D-10Q", "10-Q", "2026-08-12", "2026-06-30"),
        ("D-8K", "8-K", "2026-08-06", "2026-08-05", "2.02,9.01"),
    ])
    facts = _facts(Revenues=[_fact("D-10Q", "10-Q", "2026-08-12", "2026-04-01", "2026-06-30", 1.0, 2026, "Q2")])
    [ev] = earnings.events(subs, facts, readings={"D-8K": _read("results")})
    assert ev["day"] == "2026-08-05" and ev["release"]["filed"] == "2026-08-06"
    subs6 = _subs([("F-6K", "6-K", "2025-05-29", "2025-05-29", "", "f.htm")])
    [ev6] = earnings.events(subs6, {}, readings={"F-6K": _read("results", stated="2025-05-28")})
    assert ev6["day"] == "2025-05-28"
    far = _subs([("G-6K", "6-K", "2025-05-29", "2025-05-29", "", "g.htm")])
    [ev_far] = earnings.events(far, {}, readings={"G-6K": _read("results", stated="2025-03-01")})
    assert ev_far["day"] == "2025-05-29"


def test_an_8k_that_is_something_else_is_no_mark_and_a_preliminary_alone_is_none():
    subs = _subs([
        ("T-8K", "8-K", "2026-10-02", "2026-10-02", "2.02,9.01"),
        ("S-8K", "8-K", "2026-10-05", "2026-10-05", "2.02,7.01,9.01"),
    ])
    out = earnings.events(subs, {}, readings={"T-8K": _read("other"), "S-8K": _read("preliminary")})
    assert out == []


def test_a_release_days_after_the_report_still_belongs_to_it_and_the_mark_is_the_first_public_day():
    subs = _subs([
        ("L-8K", "8-K", "2026-05-15", "2026-05-15", "2.02"),
        ("L-10Q", "10-Q", "2026-05-13", "2026-03-31"),
    ])
    facts = _facts(Revenues=[_fact("L-10Q", "10-Q", "2026-05-13", "2026-01-01", "2026-03-31", 1.0, 2026, "Q1")])
    [ev] = earnings.events(subs, facts)
    assert ev["day"] == "2026-05-13" and ev["release"]["day"] == "2026-05-15"


MNDR_6K = """<html><body><p>Commission File Number 001-42000</p><p>Indicate by check mark whether the registrant
files or will file annual reports under cover of Form 20-F or Form 40-F. Form 20-F &#9746; Form 40-F &#9744;</p>
<p>Mobile-health Network Solutions Announces Unaudited Interim 2026 Financial Results</p>
<p>Mobile-health Network Solutions (the &ldquo;Company&rdquo;) (Nasdaq: MNDR) today announced its unaudited
financial results for the six months ended December 31, 2025. A copy of the press release is set forth in
Exhibit 99.1.</p><p>SIGNATURES</p></body></html>"""


def test_a_foreign_issuers_results_6k_is_marked_with_its_fiscal_half_and_the_later_tagged_revenue():
    reading = release_text.read_6k(MNDR_6K)
    assert reading and reading["kind"] == "results" and reading["months"] == 6 and reading["end"] == "2025-12-31"
    subs = _subs([
        ("M-F1A", "F-1/A", "2026-04-17", ""),
        ("M-6K", "6-K", "2026-03-12", "2026-03-12", "", "form6-k.htm"),
        ("M-20F", "20-F", "2025-10-31", "2025-06-30"),
    ], fye="0630")
    facts = _facts(RevenueFromContractWithCustomerExcludingAssessedTax=[
        _fact("M-20F", "20-F", "2025-10-31", "2024-07-01", "2025-06-30", 7_646_739, 2025, "FY"),
        _fact("M-F1A", "F-1/A", "2026-04-17", "2025-07-01", "2025-12-31", 3_948_768),
    ])
    out = earnings.events(subs, facts, readings={"M-6K": reading})
    h1 = next(e for e in out if e["day"] == "2026-03-12")
    assert h1["period_label"] == "2026 H1" and h1["period_end"] == "2025-12-31" and h1["period_months"] == 6
    assert h1["revenue"] == {"value": 3_948_768.0, "unit": "USD", "form": "F-1/A", "filed": "2026-04-17",
                             "period_end": "2025-12-31"}
    assert h1["report"] is None and h1["report_pending"] is True
    assert "unaudited financial results" in h1["said"] or "Financial Results" in h1["said"]


def test_a_named_quarter_6k_claims_the_interim_xbrl_report_of_its_period():
    subs = _subs([
        ("X-6K-XBRL", "6-K", "2025-09-10", "2025-06-30", "", "x.htm"),
        ("X-6K-PR", "6-K", "2025-09-02", "2025-09-02", "", "pr.htm"),
        ("X-6K-DLV", "6-K", "2025-09-01", "2025-09-01", "", "dlv.htm"),
    ])
    facts = _facts(Revenues=[_fact("X-6K-XBRL", "6-K", "2025-09-10", "2025-01-01", "2025-06-30", 4.3e9, 2025, "Q2")])
    readings = {"X-6K-PR": _read("results", said="Reports Unaudited Second Quarter 2025 Financial Results",
                                 months=3, named="2025 Q2"),
                "X-6K-DLV": None, "X-6K-XBRL": None}
    [ev] = earnings.events(subs, facts, readings=readings)
    assert ev["day"] == "2025-09-02" and ev["release"]["accession"] == "X-6K-PR"
    assert ev["report"]["accession"] == "X-6K-XBRL" and ev["period_label"] == "2025 H1"


def test_reports_from_before_the_releases_were_read_are_left_out():
    subs = _subs([("Q-20F", "20-F", "2024-10-23", "2024-06-30"), ("Q-20F2", "20-F", "2025-10-31", "2025-06-30")],
                 fye="0630")
    facts = _facts(Revenues=[
        _fact("Q-20F", "20-F", "2024-10-23", "2023-07-01", "2024-06-30", 1.0, 2024, "FY"),
        _fact("Q-20F2", "20-F", "2025-10-31", "2024-07-01", "2025-06-30", 2.0, 2025, "FY"),
    ])
    out = earnings.events(subs, facts, releases_known_since=date(2024, 9, 12))
    assert [e["day"] for e in out] == ["2025-10-31"]


def test_older_pages_reach_back_to_the_window():
    subs = _subs([], files=[{"name": "CIK0000000001-submissions-001.json", "filingTo": "2023-01-05"},
                            {"name": "CIK0000000001-submissions-002.json", "filingTo": "2014-03-01"}])
    assert earnings.older_pages(subs, date(2016, 10, 1)) == [("CIK0000000001-submissions-001.json", date(2023, 1, 5))]


def test_fiscal_labels_follow_the_registrants_year_end():
    assert fiscal.fiscal_label(date(2025, 12, 31), 6, (6, 30), 0) == "2026 H1"
    assert fiscal.fiscal_label(date(2026, 6, 27), 3, (9, 26), 0) == "2026 Q3"
    assert fiscal.fiscal_label(date(2025, 12, 31), 12, (12, 31), 0) == "2025 FY"
    assert fiscal.quarter_end("2026 Q2", (12, 31), 0) == date(2026, 6, 30)
    assert fiscal.quarter_end("2026 Q2", (6, 30), 0) == date(2025, 12, 31)


# -- which filings report results ----------------------------------------------------------------------------


def _cover(body: str) -> str:
    return f"<p>Form 20-F &#9746; Form 40-F &#9744;</p><p>{body}</p><p>SIGNATURES</p>"


@pytest.mark.parametrize("body, months, end, named", [
    ("EXHIBIT INDEX Exhibit No. Description 99.1 NIO Inc. Reports Unaudited Second Quarter 2026 Financial Results",
     3, None, "2026 Q2"),
    ("Exhibit 99.1 Condensed Consolidated Interim Financial Statements for the Three and Six Months Ended June 30, "
     "2025", 3, "2025-06-30", None),
    ("On September 1, 2026, we published our unaudited financial results for the second quarter and six months "
     "ended June 30, 2026 as our interim report.", 3, "2026-06-30", None),
    ("today announced its unaudited financial results for the six months ended December 31, 2025.",
     6, "2025-12-31", None),
])
def test_results_6ks_are_read_with_their_period(body, months, end, named):
    reading = release_text.read_6k(_cover(body))
    assert reading is not None and reading["kind"] == "results"
    assert (reading["months"], reading["end"], reading["named"]) == (months, end, named)


@pytest.mark.parametrize("body", [
    "EXHIBIT INDEX 99.1 NIO Inc. to Report Unaudited Second Quarter 2026 Financial Results on September 1, 2026",
    "EXHIBIT INDEX 99.1 NIO Inc. Provides August 2026 Delivery Update",
    "99.1 Announcement of Annual General Meeting Results and Voting Results",
    "Issuance of Class A Ordinary Shares to Key Personnel. The Board approved the allotment of 1,120,000 shares.",
    "The Company will host a conference call to discuss its second quarter 2026 financial results.",
])
def test_other_6ks_are_not_results(body):
    assert release_text.read_6k(_cover(body)) is None


def test_a_6k_that_only_attaches_a_press_release_is_read_from_its_exhibit():
    cover = _cover("On August 12, 2025, NANO-X IMAGING LTD issued a press release, a copy of which is attached "
                   "hereto as Exhibit 99.1. In the press release the Company uses certain financial measures that "
                   "are not prepared in accordance with generally accepted accounting principles.")
    reading = release_text.read_6k(cover)
    assert reading["kind"] == "unknown" and reading["stated"] == "2025-08-12"
    exhibit = release_text.read_exhibit("<p>Nano-X Imaging Reports Second Quarter 2025 Financial Results</p>")
    merged = release_text.merge(reading, exhibit)
    assert merged["kind"] == "results" and merged["named"] == "2025 Q2" and merged["stated"] == "2025-08-12"
    assert release_text.read_6k(_cover("Alibaba Group Announces June Quarter 2026 Results"))["kind"] == "results"


def _eight_k(section: str) -> str:
    return ("<p>FORM 8-K Date of Report (Date of earliest event reported)</p><p>Item 2.02 Results of Operations "
            f"and Financial Condition.</p><p>{section}</p><p>Item 9.01 Financial Statements and Exhibits.</p>")


@pytest.mark.parametrize("section, items, kind", [
    ("On July 30, 2026, Apple Inc. issued a press release regarding Apple's financial results for its third "
     "fiscal quarter ended June 27, 2026.", "2.02,9.01", "results"),
    ("On August 6, 2026, MARA Holdings, Inc. issued a shareholder letter announcing its financial results for the "
     "fiscal quarter ended June 30, 2026. The Company also issued a press release announcing its earnings webcast "
     "and conference call to be held on August 6, 2026.", "2.02,9.01", "results"),
    ("On March 6, 2025, BigBear.ai Holdings, Inc. announced its financial results of operations for the quarter "
     "and the year ended December 31, 2024.", "2.02,8.01", "results"),
    ("As described in Item 4.02 of this Current Report, the Company has identified the need to restate certain "
     "Prior Financial Statements.", "2.02,4.02", "other"),
    ("On November 4, 2025, the Company issued a press release announcing certain financial results for the "
     "fiscal quarter ended September 30, 2025.", "1.01,2.02,3.02,7.01,9.01", "preliminary"),
    ("On October 5, 2026, Lucid Group, Inc. issued a press release announcing its production and delivery totals "
     "for the quarter ended September 30, 2026.", "2.02,9.01", "other"),
    ("On January 22, 2025, AST SpaceMobile, Inc. announced a proposed private offering of convertible senior "
     "notes due 2032.", "2.02,3.02,7.01,8.01,9.01", "other"),
    ("On October 5, 2026, Serve Robotics Inc. made available on its website a Company investor presentation "
     "that may be used in presentations to investors.", "2.02,7.01,9.01", "other"),
    ("On October 2, 2026, Tesla, Inc. published the press release which is attached hereto as Exhibit 99.1 and "
     "is incorporated herein by reference.", "2.02,9.01", "unknown"),
])
def test_item_202_8ks_say_what_they_are(section, items, kind):
    assert release_text.read_8k(_eight_k(section), items)["kind"] == kind


@pytest.mark.parametrize("body", [
    "TABLE OF CONTENTS Exhibit 99.1 Press release: XPENG Announces Vehicle Delivery Results for July 2026",
    "EXHIBIT INDEX Exhibit No. Description 99.1 Press Release \u2014 NIO Inc. Announces Profit Alert for the Fourth "
    "Quarter of 2025 99.2 Announcement with The Stock Exchange of Hong Kong Limited",
])
def test_deliveries_and_profit_alerts_are_not_results(body):
    reading = release_text.read_6k(_cover(body))
    assert reading is None or reading["kind"] == "unknown"


def test_a_date_to_come_in_an_exhibit_is_not_results_even_in_its_link():
    exhibit = ("<p>EX-99.1 2 ex991.htm NEWS RELEASE DATED JULY 10, 2025 Exhibit 99.1 SNDL to Announce Second Quarter "
               "2025 Financial Results on July 31, 2025</p><p>SNDL Inc. announced today that it will release its "
               "second quarter 2025 financial results before market open.</p><p>View original content: "
               "https://www.prnewswire.com/news-releases/sndl-to-announce-second-quarter-2025-financial-results.html</p>")
    assert release_text.read_exhibit(exhibit)["kind"] == "other"
    profit_alert = ("<p>Exhibit 99.1 NIO Inc. Announces Profit Alert for the Fourth Quarter of 2025</p><p>As of the "
                    "date of this press release, the Company is in the process of preparing and finalizing the "
                    "financial results for the three months ended December 31, 2025.</p>")
    assert release_text.read_exhibit(profit_alert)["kind"] == "other"


def test_a_date_to_come_in_the_title_rules_out_the_lines_below_it():
    # SNDL 2025-04-15: the title says a date to come; its third line reads like results.
    exhibit = ("<p>EX-99.1 2 ex991.htm NEWS RELEASE DATED APRIL 14, 2025 Exhibit 99.1 SNDL to Announce First "
               "Quarter 2025 Financial Results on May 1, 2025 EDMONTON, AB, April 14, 2025 /CNW/ - SNDL Inc. "
               "(Nasdaq: SNDL) announced today that it will release its first quarter 2025 financial results before "
               "market open on May 1, 2025.</p><p>Following the release of its first quarter results, SNDL will "
               "host a conference call and webcast at 10:00 a.m. ET.</p>")
    assert release_text.read_exhibit(exhibit)["kind"] == "other"


def test_a_results_title_that_also_names_its_call_is_results():
    exhibit = ("<p>EX-99.1 2 ea024649101ex99-1_nano.htm PRESS RELEASE, DATED AUGUST 12, 2025 Exhibit 99.1 Nanox "
               "Announces Second Quarter of 2025 Financial Results and Provides Business Update Management to host "
               "conference call and webcast Tuesday, August 12, 2025 at 8:30 AM ET</p>")
    assert release_text.read_exhibit(exhibit)["kind"] == "results"
    mara = _eight_k("On February 26, 2026, MARA Holdings, Inc. issued a shareholder letter announcing its "
                    "preliminary, unaudited financial results for the fiscal quarter and full year ended December 31, "
                    "2025.")
    assert release_text.read_8k(mara, "2.02,9.01")["kind"] == "results"


def test_a_notice_that_refers_back_to_results_is_not_a_release():
    notice = ("<p>Exhibit 99.1 Hong Kong Exchanges and Clearing Limited take no responsibility for the contents of "
              "this announcement.</p><p>ADJUSTMENT TO THE CONVERSION RATE OF THE CONVERTIBLE SENIOR NOTES DUE "
              "2031.</p><p>Reference is made to the announcement of our March quarter 2025 and fiscal year 2025 "
              "results dated May 15, 2025.</p>")
    assert release_text.read_exhibit(notice)["kind"] != "results"
    cover = _cover("EXHIBITS Exhibit 99.1 - Announcement - Adjustment to the Conversion Rate of the Convertible "
                   "Senior Notes Due 2031. Further reference is made to the announcement of our March quarter 2026 "
                   "and fiscal year 2026 results dated May 13, 2026.")
    reading = release_text.read_6k(cover)
    assert reading is None or reading["kind"] == "unknown"


def test_a_later_filing_for_a_period_already_marked_is_listed_on_that_mark():
    subs = _subs([
        ("X-interim", "6-K", "2026-09-28", "2026-09-28", "", "ir.htm"),
        ("X-q2", "6-K", "2026-08-24", "2026-08-24", "", "pr.htm"),
    ])
    readings = {"X-q2": _read("results", months=3, end="2026-06-30", named="2026 Q2"),
                "X-interim": _read("results", months=6, end="2026-06-30",
                                   said="Exhibit 99.1 Interim Report for the six months ended June 30, 2026")}
    [ev] = earnings.events(subs, {}, readings=readings)
    assert ev["day"] == "2026-08-24" and [r["accession"] for r in ev["other_releases"]] == ["X-interim"]


def test_a_later_results_release_keeps_its_own_mark():
    # NNOX 2026: an earlier filing read as results must never hide the quarter's real release.
    subs = _subs([
        ("N-results", "6-K", "2026-09-09", "2026-06-30", "", "r.htm"),
        ("N-early", "6-K", "2026-08-06", "2026-08-06", "", "e.htm"),
    ])
    readings = {"N-early": _read("results", months=3, end="2026-06-30"),
                "N-results": _read("results", months=3, end="2026-06-30",
                                   said="announced its financial results for the second quarter ended June 30, 2026")}
    assert [e["day"] for e in earnings.events(subs, {}, readings=readings)] == ["2026-08-06", "2026-09-09"]


def test_an_offering_6k_with_a_caveat_on_estimates_is_not_results():
    cover = _cover("CONTENTS Registered Direct Offering On August 5, 2026, NANO-X IMAGING LTD entered into a "
                   "securities purchase agreement with a single long-term institutional investor. The preliminary "
                   "estimates are unaudited. Accordingly, the Company's final reported financial results for the "
                   "period may differ, potentially materially, from the preliminary estimates.")
    assert release_text.read_6k(cover) is None


def test_an_exhibit_about_deliveries_is_not_results():
    title = "<p>Tesla Vehicle Production &amp; Deliveries and Date for Financial Results &amp; Webcast for Third Quarter 2026</p>"
    assert release_text.read_exhibit(title)["kind"] == "other"


# -- splits ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("ratio, words", [(0.02, (1, 50, True)), (2.0, (2, 1, False)), (1.5, (3, 2, False)),
                                          (0.166667, (1, 6, True)), (0.15, (3, 20, True))])
def test_split_ratios_name_whole_shares(ratio, words):
    got = splits.shares(ratio)
    assert (got["new_shares"], got["old_shares"], got["reverse"]) == words


def test_a_stock_dividend_keeps_its_ratio_and_a_non_split_is_none():
    got = splits.shares(1.036932668)
    assert got["new_shares"] is None and got["ratio"] == pytest.approx(1.036932668)
    assert splits.shares(1.0) is None and splits.shares(0) is None and splits.shares("x") is None


def test_lists_merge_into_one_split_and_name_each_source():
    massive = [{"ticker": "MNDR", "execution_date": "2026-06-29", "split_from": 6, "split_to": 1},
               {"ticker": "MNDR", "execution_date": "2025-03-10", "split_from": 8, "split_to": 1}]
    confirmed = [{"ticker": "MNDR", "execution_date": "2024-01-02", "split_from": 4, "split_to": 1}]
    yahoo = [(datetime(2026, 6, 29, 9, 30), 1 / 6), (datetime(2025, 3, 11, 9, 30), 0.125),
             (datetime(2023, 5, 1, 9, 30), 2.0)]
    out = splits.events(massive=massive, confirmed=confirmed, yahoo=yahoo)
    by_day = {e["day"]: e for e in out}
    assert by_day["2026-06-29"]["sources"] == ["massive", "yahoo"] and by_day["2026-06-29"]["disagreement"] is None
    assert by_day["2025-03-10"]["disagreement"] == "Yahoo lists it on 2025-03-11"
    assert by_day["2024-01-02"]["sources"] == ["sec_confirmed"]
    assert by_day["2023-05-01"]["sources"] == ["yahoo"] and by_day["2023-05-01"]["reverse"] is False


def test_a_ratio_the_lists_disagree_on_is_said_never_dropped():
    massive = [{"execution_date": "2025-02-24", "split_from": 20, "split_to": 1}]
    out = splits.events(massive=massive, yahoo=[(date(2025, 2, 24), 0.2)])
    assert len(out) == 1 and out[0]["old_shares"] == 20 and out[0]["disagreement"] == "Yahoo lists 1 for 5"


# -- the route's cut at the desk's clock ----------------------------------------------------------------------


def test_a_replay_shows_nothing_from_its_own_day_or_later_but_the_days_split():
    view = {"status": "read", "symbol": "X",
            "earnings": {"status": "read", "events": [
                {"kind": "earnings", "id": "e1", "day": "2026-07-14"},
                {"kind": "earnings", "id": "e2", "day": "2026-07-15"},
                {"kind": "earnings", "id": "e3", "day": "2026-08-01"}]},
            "splits": {"status": "read", "events": [
                {"kind": "split", "id": "s1", "day": "2026-07-15"},
                {"kind": "split", "id": "s2", "day": "2026-08-24"}]}}
    playhead = datetime(2026, 7, 15, 10, 0, tzinfo=ET).timestamp()
    out = routes.answer(view, playhead)
    assert out["replay"] is True and out["through"].startswith("2026-07-15T10:00")
    assert [e["id"] for e in out["earnings"]["events"]] == ["e1"]
    assert [e["id"] for e in out["splits"]["events"]] == ["s1"]
    live = routes.answer(view, None)
    assert live["replay"] is False and len(live["earnings"]["events"]) == 3


# -- the reader -----------------------------------------------------------------------------------------------


def _reader(tmp_path: Path, fetch, yahoo, massive: list | None):
    massive_path = tmp_path / "splits.json"
    if massive is not None:
        massive_path.write_text(json.dumps(massive), encoding="utf-8")
    return ChartEventsReader(fetch=fetch, yahoo=yahoo, list_paths=lambda: (massive_path, tmp_path / "none.json"),
                             clock=lambda: datetime(2026, 10, 12, 12, 0).timestamp(), sleep=lambda _s: None,
                             run_inline=True)


def test_the_reader_answers_both_parts_and_names_what_it_could_not_read(tmp_path):
    subs = _subs([("A-8K", "8-K", "2026-07-30", "2026-07-30", "2.02"), ("A-10Q", "10-Q", "2026-07-31", "2026-06-27")])
    facts = _facts(Revenues=[_fact("A-10Q", "10-Q", "2026-07-31", "2026-03-29", "2026-06-27", 7.0, 2026, "Q3")])
    replies = {"company_tickers.json": {"0": {"ticker": "AAPL", "cik_str": 320193}},
               "CIK0000320193.json": subs, "companyfacts/CIK0000320193.json": facts}

    def fetch(url, headers):
        assert "User-Agent" in headers
        return json.dumps(next(v for k, v in replies.items() if url.endswith(k))).encode()

    def yahoo(_symbol):
        raise TimeoutError("Yahoo did not answer")

    reader = _reader(tmp_path, fetch, yahoo, [{"ticker": "AAPL", "execution_date": "2020-08-31",
                                               "split_from": 1, "split_to": 4}])
    view = reader.view("aapl")
    assert view["status"] == "read" and view["earnings"]["events"][0]["day"] == "2026-07-30"
    assert view["splits"]["status"] == "read" and view["splits"]["events"][0]["new_shares"] == 4
    assert view["splits"]["lists"]["yahoo"]["status"] == "error"
    assert view["splits"]["lists"]["sec_confirmed"]["status"] == "absent"
    assert "Yahoo did not answer" in view["splits"]["error"]


def test_a_symbol_sec_does_not_list_has_no_earnings_and_says_why(tmp_path):
    def fetch(url, headers):
        return json.dumps({"0": {"ticker": "AAPL", "cik_str": 320193}}).encode()

    reader = _reader(tmp_path, fetch, lambda _s: [], None)
    view = reader.view("ZZZZ")
    assert view["earnings"]["status"] == "no_cik" and view["earnings"]["events"] == []
    assert view["splits"]["lists"]["massive"]["status"] == "absent" and view["splits"]["status"] == "read"
