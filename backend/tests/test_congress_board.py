"""ADR 066: the Congress overview composed from what was read (congress/board.py, congress/views.py)."""
from datetime import date

from congress import board, views
from congress.state import Book

TODAY = date(2026, 10, 14)
ROSTER = [
    {"bioguide": "S000001", "name": "Sen One", "first": "Sen", "last": "One", "party": "D", "caucus": None, "state": "AA",
     "district": None, "chamber": "senate", "current": True, "left": None, "committees": ["Committee on Finance"]},
    {"bioguide": "S000002", "name": "Sen Two", "first": "Sen", "last": "Two", "party": "R", "caucus": None, "state": "BB",
     "district": None, "chamber": "senate", "current": False, "left": "2026-03-23", "committees": []},
    {"bioguide": "H000001", "name": "Rep One", "first": "Rep", "last": "One", "party": "R", "caucus": None, "state": "CC",
     "district": 6, "chamber": "house", "current": True, "left": None, "committees": []},
    {"bioguide": "H000002", "name": "Rep Two", "first": "Rep", "last": "Two", "party": "D", "caucus": None, "state": "DD",
     "district": 1, "chamber": "house", "current": True, "left": None, "committees": []},
    {"bioguide": "H000003", "name": "Del Three", "first": "Del", "last": "Three", "party": "D", "caucus": None,
     "state": "PR", "district": 0, "chamber": "house", "current": True, "left": None, "committees": []},
]


def rep(rid, chamber, bio, filed, kind="electronic", read=True, **more):
    return {"id": rid, "chamber": chamber, "filer_name": f"filer {rid}", "filer_first": "", "filer_last": "",
            "filer_state": None, "filer_district": None, "bioguide": bio, "filed": filed, "kind": kind,
            "url": f"https://example.gov/{rid}", "title": None, "amends": None, "amended_by": None,
            "parser": 1 if read else None, "read_at": 1.0 if read else None, "error": None, "trades": 0, **more}


def row(tx, ticker, tx_type, asset_type="ST", amount="$1,001 - $15,000", description=""):
    return {"tx": tx, "notified": None, "owner": "self", "ticker": ticker, "asset": f"{ticker} Inc.",
            "asset_type": asset_type, "tx_type": tx_type, "amount": amount, "status": "New", "subholding": None,
            "description": description}


def book() -> Book:
    b = Book()
    reports = {
        "R1": rep("R1", "house", "H000001", "2026-10-12"),
        "R2": rep("R2", "senate", "S000001", "2026-08-01"),
        "R3": rep("R3", "house", "H000002", "2026-10-07", kind="paper", read=False),
        "R4": rep("R4", "senate", "S000001", "2026-08-05", amends="2024-06-14"),
        "R5": rep("R5", "senate", "S000001", "2024-06-14", amended_by="R4"),
        "R6": rep("R6", "senate", "S000002", "2026-02-01"),
    }
    rows = {
        "R1": [row("2026-09-18", "AAPL", "P"), row("2026-09-20", "MSFT", "S"),
               row("2026-09-20", "AAPL", "S (partial)", description="Contribution of 100 shares to Donor-Advised Fund.")],
        "R2": [row("2026-06-01", "AAPL", "Sale (Full)", "Stock", "$50,001 - $100,000"),
               row("2026-07-15", "NVDA", "Purchase", "Stock Option")],
        "R4": [row("2024-03-08", "XYZ", "Purchase", "Stock")],
        "R5": [row("2024-03-08", "XYZ", "Purchase", "Stock")],
        "R6": [row("2026-01-20", "IBM", "Sale (Full)", "Stock")],
    }
    b.replace(reports, rows)
    return b


def compose(filter_="all", members=None):
    board.reset_for_tests()
    version, reports, trades = book().snapshot()
    return board.compose(version, reports, trades, ROSTER, {"S000001"}, TODAY, filter_, members, 1.0)


def test_counts_skip_gifts_and_an_amendments_old_trades():
    out = compose()
    assert out["counts"] == {"all": 6, "house": 3, "senate": 3, "buys": 2, "sells": 3, "options": 1, "late": 1}
    assert out["periods"]["30d"]["from"] == "2026-09-14"


def test_most_traded_counts_members_and_skips_gifts():
    top = compose()["most_traded"]["ytd"]
    assert top[0] == {"ticker": "AAPL", "asset": "AAPL Inc.", "members": 2, "buyers": ["H000001"],
                      "sellers": ["S000001"], "buys": 1, "sells": 1}
    assert {t["ticker"] for t in top} == {"AAPL", "MSFT", "NVDA", "IBM"}           # XYZ: reported in 2024
    assert [t["ticker"] for t in compose()["most_traded"]["30d"]] == ["AAPL", "MSFT"]


def test_who_reported_in_each_period():
    out = compose()
    assert out["reported"]["ytd"] == {"H000001": "trades", "S000001": "trades", "S000002": "trades", "H000002": "paper"}
    assert out["reported"]["30d"] == {"H000001": "trades", "H000002": "paper"}
    assert compose("buys")["reported"]["30d"] == {"H000001": "trades"}            # a paper report holds no known buy


def test_just_reported_newest_first_with_its_biggest_trade():
    out = compose()
    assert [r["id"] for r in out["just_reported"]] == ["R1", "R3", "R4", "R2", "R6"]
    r1 = out["just_reported"][0]
    assert r1["member"]["bioguide"] == "H000001" and r1["trades"] == 3 and r1["top"]["ticker"] in ("AAPL", "MSFT")
    paper = out["just_reported"][1]
    assert paper["kind"] == "paper" and paper["read"] is False and paper["top"] is None
    assert out["just_reported"][2]["amends"] == "2024-06-14"
    assert [r["id"] for r in compose("buys")["just_reported"]] == ["R1", "R4", "R2"]


def test_lag_and_late():
    lag = compose()["lag"]
    assert lag["trades"] == 6 and lag["median_days"] == 22.0               # 12, 17, 22, 22, 24, 61 days
    assert lag["after_limit_pct"] == round(100 / 6, 1) and lag["limit_days"] == 45
    assert sum(lag["buckets"]) == 6 and len(lag["buckets"]) == 25


def test_seats_and_who_left():
    seats = compose()["seats"]
    assert [m["bioguide"] for m in seats["senate"]] == ["S000001"] and seats["empty"]["senate"] == 99
    assert [m["bioguide"] for m in seats["house"]] == ["H000001", "H000002"]
    assert [m["bioguide"] for m in seats["delegates"]] == ["H000003"]
    assert [(m["bioguide"], m["left"]) for m in seats["former"]] == [("S000002", "2026-03-23")]
    assert seats["senate"][0]["photo"] is True and seats["house"][0]["photo"] is False


def test_the_following_tab_counts_only_its_members():
    out = compose(members=frozenset({"S000001"}))
    assert {t["ticker"] for t in out["most_traded"]["ytd"]} == {"AAPL", "NVDA"}
    assert out["counts"]["all"] == 6                                            # the tabs' counts stay whole
    assert [a["bioguide"] for a in out["most_active"]] == ["S000001"]


def test_most_active_has_weeks_and_its_top_tickers():
    active = compose()["most_active"]
    assert active[0]["bioguide"] == "H000001" and active[0]["trades"] == 3
    assert active[0]["buys"] == 1 and active[0]["sells"] == 1                   # the gift is neither
    assert len(active[0]["weeks"]["buy"]) == 26 and sum(active[0]["weeks"]["buy"]) == 1


def test_a_members_page_and_a_tickers_page():
    version, reports, trades = book().snapshot()
    roster = {m["bioguide"]: m for m in ROSTER}
    page = views.member("S000001", reports, trades, roster, set(), TODAY)
    assert page["member"]["committees"] == ["Committee on Finance"]
    assert page["member"]["ytd"]["trades"] == 2                                 # R4's trades are 2024's
    assert [r["id"] for r in page["reports"]] == ["R4", "R2", "R5"]
    assert {t["ticker"] for t in page["trades"]} == {"AAPL", "NVDA", "XYZ"}
    assert views.member("Z999999", reports, trades, roster, set(), TODAY) is None
    aapl = views.ticker("AAPL", trades, roster, set())
    assert aapl["buyers"] == ["H000001"] and aapl["sellers"] == ["S000001"] and len(aapl["trades"]) == 3
    everyone = views.members(reports, trades, ROSTER, set(), TODAY)
    assert [m["bioguide"] for m in everyone][:2] == ["H000001", "S000001"]
    assert "S000002" in {m["bioguide"] for m in everyone}                       # left, but reported
