"""The front door's cash-runway read (``research/market_reads/runway.py``, ADR 059, #1102): cash, burn, runway, share
growth and offering filings as known on a past day -- nothing from after it, every figure labelled with its period and
filing date, unknown null and never 0, and a runway only from one quarter's cash and burn."""
from __future__ import annotations

import json
import sys
import zipfile
from datetime import date
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research"))

from market_reads import runway, sec, splits, tickers  # noqa: E402

CIK = "555"
DAY = "2024-06-15"


def _statement(period: str, filed: str, timeframe: str = "quarterly", cik: str = "0000000555",
               ticker: str = "RUNW", **figures) -> dict:
    return {"tickers": [ticker], "cik": cik, "period_end": period, "filing_date": filed, "timeframe": timeframe,
            "fiscal_year": int(period[:4]), "fiscal_quarter": 1, **figures}


def _fact(end: str, filed: str, val: int, form: str = "10-Q") -> dict:
    return {"end": end, "filed": filed, "val": val, "form": form}


STANDARD_BALANCE = [
    _statement("2023-12-31", "2024-02-20", cash_and_equivalents=800.0, short_term_investments=100.0),
    _statement("2024-03-31", "2024-05-10", cash_and_equivalents=600.0, short_term_investments=400.0),
]
STANDARD_FLOWS = [
    _statement("2023-12-31", "2024-02-20", net_cash_from_operating_activities=-150.0),
    _statement("2024-03-31", "2024-05-10", net_cash_from_operating_activities=-300.0),
    _statement("2023-12-31", "2024-02-20", "annual", net_cash_from_operating_activities=-700.0),
    _statement("2024-03-31", "2024-05-10", "trailing_twelve_months", net_cash_from_operating_activities=-650.0),
]
STANDARD_COUNTS = [("2023-05-10", 700_000), ("2023-11-10", 800_000), ("2024-05-10", 900_000),
                   ("2024-11-10", 1_000_000), ("2025-05-10", 1_200_000)]
STANDARD_FILINGS = [  # (form, filed, items)
    ("S-1", "2020-01-01", ""), ("S-3", "2022-03-01", ""), ("424B5", "2023-08-01", ""), ("8-K", "2024-01-15", "1.01"),
    ("4", "2024-02-02", ""), ("8-K", "2024-04-20", "3.02,9.01"), ("424B5", "2024-06-20", "")]


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


@pytest.fixture
def world(tmp_path, monkeypatch):
    """Builds a fake reference dump + SEC bulk files + split table; returns the function that fills them."""
    monkeypatch.setenv("NOVA_MARKET_DATA_DIR", str(tmp_path / "massive"))
    monkeypatch.setenv("NOVA_CATALYST_DIR", str(tmp_path / "catalysts"))
    state = {"splits": pd.DataFrame({"execution_date": pd.Series([], dtype=object),
                                     "price_factor": pd.Series([], dtype=float)})}
    monkeypatch.setattr(splits, "table", lambda symbol=None, day=None, cik=None: state["splits"])
    monkeypatch.setattr(tickers, "_filing_span", lambda cik: None)

    def build(balance=STANDARD_BALANCE, flows=STANDARD_FLOWS, counts=STANDARD_COUNTS, filings=STANDARD_FILINGS,
              listings=None, split_rows=None, submissions=True):
        ref = tmp_path / "massive" / "store" / "reference"
        other = [_statement("2024-03-31", "2024-05-10", ticker="OTHR", cik="0000000777", cash_and_equivalents=5.0)]
        _write(ref / "balance_sheets" / "2024-05.jsonl", [*balance, *other])
        _write(ref / "cash_flow_statements" / "2024-05.jsonl", [*flows, *other])
        (ref / "tickers.json").write_text(json.dumps(listings or [
            {"ticker": "RUNW", "cik": "0000000555", "name": "Runway Co", "active": True},
            {"ticker": "OTHR", "cik": "0000000777", "name": "Other Co", "active": True},
            {"ticker": "NOSTM", "cik": "0000000888", "name": "No Statements Co", "active": True}]), encoding="utf-8")
        edgar = tmp_path / "catalysts" / "edgar"
        edgar.mkdir(parents=True, exist_ok=True)
        facts = {"entityName": "Runway Co", "facts": {"dei": {"EntityCommonStockSharesOutstanding": {
            "units": {"shares": [_fact(end, f"{end[:8]}{int(end[8:]) + 3:02d}", val) for end, val in counts]}}}}}
        subs = {"name": "Runway Co", "filings": {"recent": {
            "form": [f[0] for f in filings], "filingDate": [f[1] for f in filings],
            "reportDate": ["" for _ in filings], "accessionNumber": [f"acc-{i}" for i, _ in enumerate(filings)],
            "items": [f[2] for f in filings]}}}
        with zipfile.ZipFile(edgar / "companyfacts.zip", "w") as z:
            z.writestr("CIK0000000555.json", json.dumps(facts))
        with zipfile.ZipFile(edgar / "submissions.zip", "w") as z:
            if submissions:
                z.writestr("CIK0000000555.json", json.dumps(subs))
        if split_rows is not None:
            state["splits"] = pd.DataFrame({"execution_date": [date.fromisoformat(d) for d, _ in split_rows],
                                            "price_factor": [f for _, f in split_rows]})
        sec._zip.cache_clear()
        tickers.clear()

    yield build
    sec._zip.cache_clear()
    tickers.clear()


def test_the_runway_divides_one_quarters_cash_by_its_monthly_burn_and_names_every_period(world):
    world()
    a = runway.runway("runw", DAY)
    assert a["cik"] == CIK and a["entity"] == "Runway Co" and a["symbol"] == "RUNW"
    assert a["cash"] == {"cash_and_equivalents": 600.0, "short_term_investments": 400.0, "liquid": 1000.0,
                         "liquid_basis": "cash_and_equivalents + short_term_investments", "timeframe": "quarterly",
                         "period_end": "2024-03-31", "filing_date": "2024-05-10", "age_days": 76, "stale": False}
    assert a["burn"]["operating_cash_flow"] == -300.0 and a["burn"]["burn"] == 300.0
    assert (a["burn"]["period_end"], a["burn"]["filing_date"]) == ("2024-03-31", "2024-05-10")
    assert a["burn"]["field"] == "net_cash_from_operating_activities" and a["burn"]["stale"] is False
    assert [q["operating_cash_flow"] for q in a["burn"]["recent_quarters"]] == [-300.0, -150.0]   # no annual / TTM rows
    assert a["runway"]["months"] == 10.0 and a["runway"]["status"] == "computed"      # 1000 / (300 / 3)
    assert a["runway"]["period_gap_days"] == 0 and a["runway"]["stale"] is False and a["notes"] == []


def test_a_statement_filed_after_the_day_is_not_known_yet(world):
    world()
    a = runway.runway("RUNW", "2024-05-09")             # Q1 was filed 2024-05-10
    assert a["cash"]["period_end"] == "2023-12-31" and a["cash"]["liquid"] == 900.0
    assert a["burn"]["operating_cash_flow"] == -150.0
    assert a["runway"]["months"] == 18.0                 # 900 / (150 / 3)
    on_the_day = runway.runway("RUNW", "2024-05-10")
    assert on_the_day["cash"]["period_end"] == "2024-03-31"          # a filing counts from its filing day
    assert runway.runway("RUNW", "2024-02-19")["cash"] is None       # nothing filed yet: unknown, not zero


def test_unknown_is_null_never_zero(world):
    world()
    nothing = runway.runway("NOSTM", DAY)
    assert nothing["cash"] is None and nothing["burn"] is None and nothing["runway"]["months"] is None
    assert nothing["runway"]["status"] == "no_balance_sheet" and nothing["runway"]["stale"] is None
    assert nothing["shares"]["outstanding"] is None and nothing["shares"]["growth_4q"]["status"] == "no_count_now"
    assert nothing["offerings"] is None and any("offerings unknown" in n for n in nothing["notes"])
    world(balance=[_statement("2024-03-31", "2024-05-10", cash_and_equivalents=600.0)], flows=[])
    only_cash = runway.runway("RUNW", DAY)
    assert only_cash["cash"]["short_term_investments"] is None and only_cash["cash"]["liquid"] == 600.0
    assert only_cash["cash"]["liquid_basis"] == "cash_and_equivalents only: no short-term investments reported"
    assert only_cash["burn"] is None and only_cash["runway"]["status"] == "no_cash_flow_statement"
    world(balance=[_statement("2024-03-31", "2024-05-10", receivables=3.0)])
    no_cash = runway.runway("RUNW", DAY)
    assert no_cash["cash"]["liquid"] is None and no_cash["cash"]["cash_and_equivalents"] is None
    assert no_cash["runway"]["status"] == "cash_not_reported" and no_cash["runway"]["months"] is None
    world(flows=[_statement("2024-03-31", "2024-05-10", net_income=-5.0)])
    no_flow = runway.runway("RUNW", DAY)
    assert no_flow["burn"]["operating_cash_flow"] is None and no_flow["burn"]["burn"] is None
    assert no_flow["runway"]["status"] == "operating_cash_flow_not_reported"


def test_the_continuing_operations_figure_stands_in_and_says_so(world):
    world(flows=[_statement("2024-03-31", "2024-05-10", cash_from_operating_activities_continuing_operations=-90.0)])
    a = runway.runway("RUNW", DAY)
    assert a["burn"]["operating_cash_flow"] == -90.0
    assert a["burn"]["field"] == "cash_from_operating_activities_continuing_operations"


def test_a_cash_generating_quarter_has_no_burn_and_no_runway(world):
    world(flows=[_statement("2024-03-31", "2024-05-10", net_cash_from_operating_activities=40.0)])
    a = runway.runway("RUNW", DAY)
    assert a["burn"]["operating_cash_flow"] == 40.0 and a["burn"]["burn"] is None      # signed as filed
    assert a["runway"]["months"] is None and a["runway"]["status"] == "no_burn"
    assert a["cash"]["liquid"] == 1000.0                                                # cash stays in the answer


def test_a_burn_from_another_quarter_is_not_divided_into_todays_cash(world):
    """Massive dates a period by the newest filing that carried it: the cash can be this spring's while the newest
    cash-flow quarter is last year's. The runway stays null, both figures stay, and the answer says why."""
    world(flows=[_statement("2023-03-31", "2024-05-10", net_cash_from_operating_activities=-300.0)])
    a = runway.runway("RUNW", DAY)
    assert a["runway"]["months"] is None and a["runway"]["status"] == "periods_far_apart"
    assert a["runway"]["period_gap_days"] == 366 and a["runway"]["stale"] is True
    assert a["burn"]["burn"] == 300.0 and a["burn"]["age_days"] == 442 and a["burn"]["stale"] is True
    assert a["cash"]["liquid"] == 1000.0 and a["cash"]["stale"] is False
    assert any("not one quarter" in n for n in a["notes"]) and any("cash-flow statement" in n for n in a["notes"])


def test_an_old_pair_from_one_quarter_is_computed_but_flagged_stale(world):
    world(balance=[_statement("2022-12-31", "2024-02-20", cash_and_equivalents=300.0)],
          flows=[_statement("2022-12-31", "2024-02-20", net_cash_from_operating_activities=-90.0)])
    a = runway.runway("RUNW", DAY)
    assert a["runway"]["months"] == 10.0 and a["runway"]["status"] == "computed" and a["runway"]["stale"] is True
    assert a["cash"]["age_days"] == 532 and len(a["notes"]) == 2          # the balance sheet and the cash flow


def test_a_period_that_ends_after_its_filing_or_the_day_counts_for_nothing(world):
    world(balance=[*STANDARD_BALANCE,
                   _statement("2024-09-30", "2024-05-11", cash_and_equivalents=9.0),     # ends after its own filing
                   _statement("2024-06-30", "2024-06-14", cash_and_equivalents=9.0)])    # ends after the day
    a = runway.runway("RUNW", DAY)
    assert a["cash"]["period_end"] == "2024-03-31"
    assert any(n.startswith("2 statement rows dropped") for n in a["notes"])


def test_shares_growth_runs_over_a_year_and_two_years_on_the_days_share_basis(world):
    world(split_rows=[("2025-01-15", 10.0)])                 # a 1-for-10 reverse split after both older counts
    a = runway.runway("RUNW", "2025-06-01")
    now = a["shares"]["outstanding"]
    assert now["value"] == 1_200_000 and now["end"] == "2025-05-10" and now["filed"] == "2025-05-13"
    four = a["shares"]["growth_4q"]
    assert four["status"] == "computed" and four["months_back"] == 12 and four["span_days"] == 365
    assert four["from"] == {"value": 90_000, "end": "2024-05-10", "filed": "2024-05-13", "form": "10-Q",
                            "split_factor": 10.0}            # 900,000 then = 90,000 on the days basis
    assert four["to"] == {"value": 1_200_000, "end": "2025-05-10", "filed": "2025-05-13", "form": "10-Q"}
    assert four["pct"] == 1233.33                            # (1,200,000 / 90,000 - 1) x 100
    eight = a["shares"]["growth_8q"]
    assert eight["status"] == "computed" and eight["span_days"] == 731 and eight["pct"] == 1614.29
    assert eight["from"]["value"] == 70_000


def test_growth_without_a_split_is_the_plain_ratio(world):
    world()
    a = runway.runway("RUNW", "2025-06-01")
    assert a["shares"]["growth_4q"]["pct"] == 33.33 and a["shares"]["growth_8q"]["pct"] == 71.43
    assert a["shares"]["growth_4q"]["from"]["split_factor"] == 1.0


def test_growth_is_null_with_its_reason_when_the_counts_are_not_a_window_apart(world):
    world()
    early = runway.runway("RUNW", DAY)          # a count a year earlier, none two years earlier
    assert early["shares"]["growth_4q"]["pct"] == 28.57 and early["shares"]["growth_8q"]["pct"] is None
    assert early["shares"]["growth_8q"]["status"] == "no_count_then" and early["shares"]["growth_8q"]["from"] is None
    world(counts=[("2023-05-10", 700_000)])     # the only count is a year old by the day: the same count then and now
    same = runway.runway("RUNW", "2024-06-15")
    assert same["shares"]["growth_4q"]["status"] == "same_count" and same["shares"]["growth_4q"]["pct"] is None
    assert same["shares"]["growth_4q"]["span_days"] == 0
    world(counts=[("2022-08-10", 500_000), ("2024-05-10", 900_000)])      # nothing between: 639 days, not a year
    gap = runway.runway("RUNW", DAY)
    assert gap["shares"]["growth_4q"]["status"] == "span_off_window" and gap["shares"]["growth_4q"]["pct"] is None
    assert gap["shares"]["growth_4q"]["span_days"] == 639 and gap["shares"]["growth_4q"]["from"]["value"] == 500_000


def test_the_filings_are_the_offering_forms_in_the_lookback_with_their_dates(world):
    world()
    a = runway.runway("RUNW", DAY)
    o = a["offerings"]
    assert o["lookback_days"] == 1095 and o["from"] == "2021-06-16" and o["through"] == DAY
    assert o["total"] == 4 and o["counts"] == {"S-3": 1, "424B5": 1, "8-K": 2}      # no S-1 (2020), Form 4, or 06-20 424B5
    assert o["latest"] == {"S-3": "2022-03-01", "424B5": "2023-08-01", "8-K": "2024-04-20"}
    assert [(f["form"], f["filed"], f["kind"]) for f in o["filings"]] == [
        ("8-K", "2024-04-20", "current_report"), ("8-K", "2024-01-15", "current_report"),
        ("424B5", "2023-08-01", "prospectus"), ("S-3", "2022-03-01", "shelf")]
    assert o["filings"][0]["items"] == "3.02,9.01" and o["filings"][0]["accession"] == "acc-5"
    assert o["truncated"] is False and "S-1/A" in o["forms"] and "4" not in o["forms"]
    narrow = runway.runway("RUNW", DAY, lookback_days=120)["offerings"]
    assert narrow["from"] == "2024-02-16" and narrow["counts"] == {"8-K": 1} and narrow["total"] == 1
    wide = runway.runway("RUNW", DAY, lookback_days=3650)["offerings"]
    assert wide["counts"]["S-1"] == 1 and wide["total"] == 5


def test_a_long_filing_list_is_cut_to_the_newest_but_counted_whole(world, monkeypatch):
    world(filings=[("8-K", f"2024-05-{d:02d}", "") for d in range(1, 11)])
    monkeypatch.setattr(runway, "MAX_FILINGS", 3)
    o = runway.runway("RUNW", DAY)["offerings"]
    assert [f["filed"] for f in o["filings"]] == ["2024-05-10", "2024-05-09", "2024-05-08"]
    assert o["truncated"] is True and o["total"] == 10 and o["counts"] == {"8-K": 10}


def test_a_company_without_a_submissions_list_has_unknown_offerings_not_none_on_file(world):
    world(submissions=False)
    a = runway.runway("RUNW", DAY)
    assert a["offerings"] is None and any("offerings unknown" in n for n in a["notes"])
    assert a["runway"]["months"] == 10.0                      # the rest of the answer is unaffected


def test_a_ticker_two_companies_used_reads_the_company_that_held_it_that_day(world):
    listings = [{"ticker": "RUNW", "cik": "0000000555", "name": "Runway Now", "active": True},
                {"ticker": "RUNW", "cik": "0000000444", "name": "Runway Then", "active": False,
                 "delisted_utc": "2020-01-10T05:00:00Z"}]
    then = [_statement("2019-09-30", "2019-11-05", cik="0000000444", cash_and_equivalents=50.0),
            *STANDARD_BALANCE]
    world(balance=then, flows=[_statement("2019-09-30", "2019-11-05", cik="0000000444",
                                          net_cash_from_operating_activities=-30.0), *STANDARD_FLOWS],
          listings=listings)
    old = runway.runway("RUNW", "2019-12-01")
    assert old["cik"] == "444" and old["cash"]["liquid"] == 50.0 and old["burn"]["burn"] == 30.0
    assert old["runway"]["months"] == 5.0 and old["ticker"]["ticker_reused"] is True
    assert old["offerings"] is None                           # CIK 444 has no submissions in the fake file
    now = runway.runway("RUNW", DAY)
    assert now["cik"] == CIK and now["cash"]["liquid"] == 1000.0
    assert runway.runway("RUNW", "2019-12-01", cik="555")["cik"] == "555"       # an asked CIK wins
    assert runway.runway("RUNW", "2019-12-01", cik="555")["cash"] is None


def test_the_answer_is_strict_json_with_no_nan(world):
    world(balance=[_statement("2024-03-31", "2024-05-10", cash_and_equivalents=float("nan"))])
    text = json.dumps(runway.runway("RUNW", DAY), allow_nan=False)
    assert "NaN" not in text


def test_a_bad_day_or_lookback_is_refused(world):
    world()
    for bad in ("2024-6-1x", "yesterday", ""):
        with pytest.raises(ValueError):
            runway.runway("RUNW", bad)
    for bad in (0, -1, 3651):
        with pytest.raises(ValueError, match="lookback_days"):
            runway.runway("RUNW", DAY, lookback_days=bad)
    with pytest.raises(LookupError, match="no SEC CIK"):
        runway.runway("ZZZZ", DAY)


def test_the_month_arithmetic_clamps_to_the_end_of_a_shorter_month():
    assert runway._months_before("2024-02-29", 12) == "2023-02-28"
    assert runway._months_before("2024-02-29", 24) == "2022-02-28"
    assert runway._months_before("2025-06-01", 12) == "2024-06-01"
    assert runway._months_before("2025-01-31", 12) == "2024-01-31"
