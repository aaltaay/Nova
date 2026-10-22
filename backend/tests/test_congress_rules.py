"""ADR 066: a Senate report's page, a trade's derived fields, and matching a filer to a member (pure parts)."""
from congress import matching, senate_html, trades

BASE = "https://efdsearch.senate.gov"
PAGE = """<html><table class="table"><thead><tr><th>#</th></tr></thead><tbody>
<tr><td>1</td><td>09/04/2026</td><td>Spouse</td><td><a href="https://finance.yahoo.com/quote/EXA">EXA</a></td>
<td>Example Bank Corp. Common Stock</td><td>Stock</td><td>Sale (Partial)</td><td>$15,001 - $50,000</td><td>--</td></tr>
<tr><td>2</td><td>09/15/2026</td><td>Child</td><td>--</td><td>EXAMPLE CORP<br/>Rate/Coupon: 5.6%</td>
<td>Corporate Bond</td><td>Purchase</td><td>$1,001 - $15,000</td><td>Called &amp; reinvested</td></tr>
</tbody></table></html>"""


def test_a_search_row_names_the_report_and_its_kind():
    r = senate_html.search_row(["Pat", "Example", "Example, Pat (Senator)",
                                '<a href="/search/view/ptr/0541be4f-4f96-4d84-8d6f-d349f218bb2a/" target="_blank">'
                                "Periodic Transaction Report for 10/07/2026</a>", "10/07/2026"], BASE)
    assert r.id == "S:0541be4f-4f96-4d84-8d6f-d349f218bb2a" and r.kind == "electronic"
    assert (r.filed, r.report_date, r.amendment) == ("2026-10-07", "2026-10-07", False)
    assert r.url == BASE + "/search/view/ptr/0541be4f-4f96-4d84-8d6f-d349f218bb2a/"


def test_an_amendment_and_a_paper_report():
    amended = senate_html.search_row(["Pat", "Example", "Example, Pat (Senator)",
                                      '<a href="/search/view/ptr/aaaaaaaa-1111-2222-3333-444444444444/">'
                                      "Periodic Transaction Report for 06/14/2024 (Amendment 1)</a>", "08/05/2026"], BASE)
    assert amended.amendment and amended.report_date == "2024-06-14" and amended.filed == "2026-08-05"
    paper = senate_html.search_row(["Pat", "Example", "Example, Pat (Senator)",
                                    '<a href="/search/view/paper/bbbbbbbb-1111-2222-3333-444444444444/">'
                                    "Periodic Transaction Report</a>", "03/02/2026"], BASE)
    assert paper.kind == "paper" and paper.report_date is None
    assert senate_html.search_row(["too", "short"], BASE) is None


def test_a_report_page_gives_its_rows_as_filed():
    rows = senate_html.parse_report(PAGE)
    assert [(r.tx_date, r.owner, r.ticker, r.asset_type, r.tx_type) for r in rows] == [
        ("2026-09-04", "Spouse", "EXA", "Stock", "Sale (Partial)"),
        ("2026-09-15", "Child", None, "Corporate Bond", "Purchase"),
    ]
    assert rows[0].comment == "" and rows[1].comment == "Called & reinvested"
    assert rows[1].asset == "EXAMPLE CORP Rate/Coupon: 5.6%"
    assert senate_html.parse_report("<html>no table</html>") is None


def _build(chamber: str, **row) -> trades.Trade:
    report = {"id": "R1", "chamber": chamber, "filed": "2026-10-01", "url": "u", "bioguide": "X000001",
              "filer_name": "Pat Example"}
    base = {"n": 0, "tx": "2026-09-01", "notified": None, "owner": "self", "ticker": "exa", "asset": "Example",
            "asset_type": "ST" if chamber == "house" else "Stock", "tx_type": "P" if chamber == "house" else "Purchase",
            "amount": "$1,001 - $15,000", "description": ""}
    return trades.build(report, {**base, **row})


def test_derived_fields_of_a_trade():
    t = _build("house")
    assert (t.kind, t.side, t.partial, t.gift, t.low, t.high, t.lag_days, t.late, t.ticker) == (
        "stock", "buy", False, False, 1001, 15000, 30, False, "EXA")
    assert trades.tradable(t)
    late = _build("senate", tx="2026-08-01", tx_type="Sale (Partial)", owner="Spouse")
    assert (late.side, late.partial, late.owner, late.lag_days, late.late) == ("sell", True, "spouse", 61, True)
    gift = _build("house", tx_type="S (partial)", description="Contribution of 7,704 shares to Donor-Advised Fund.")
    assert gift.gift and not trades.tradable(gift)
    option = _build("senate", asset_type="Stock Option")
    assert option.kind == "option" and trades.tradable(option)
    bond = _build("senate", asset_type="Municipal Security", ticker="--")
    assert bond.kind == "other" and not trades.tradable(bond)


def test_amount_ranges_as_stated():
    assert trades.amount_range("$1,001 - $15,000") == (1001, 15000)
    assert trades.amount_range("Over $50,000,000") == (50000000, None)
    assert trades.amount_range("Spouse/DC Over $1,000,000") == (1000000, None)
    assert trades.amount_range("$15.00") == (15, 15)
    assert trades.amount_range("") == (None, None)


ROSTER = [
    {"bioguide": "M001232", "first": "April", "last": "McClain Delaney", "nickname": "", "chamber": "house", "state": "MD",
     "district": 6, "current": True},
    {"bioguide": "M001190", "first": "Markwayne", "last": "Mullin", "nickname": "", "chamber": "senate", "state": "OK",
     "district": None, "current": False},
    {"bioguide": "M001225", "first": "Kevin", "last": "Mullin", "nickname": "", "chamber": "house", "state": "CA",
     "district": 15, "current": True},
    {"bioguide": "J000312", "first": "James", "last": "Justice", "nickname": "Jim", "chamber": "senate", "state": "WV",
     "district": None, "current": True},
    {"bioguide": "S000001", "first": "Ann", "last": "Smith", "nickname": "", "chamber": "house", "state": "TX",
     "district": 3, "current": True},
    {"bioguide": "S000002", "first": "Bob", "last": "Smith", "nickname": "", "chamber": "house", "state": "TX",
     "district": 9, "current": True},
]


def test_matching_a_filer_to_a_member():
    assert matching.house(ROSTER, "April McClain", "Delaney", "MD06") == "M001232"
    assert matching.house(ROSTER, "April", "McClain Delaney", "MD06") == "M001232"
    assert matching.house(ROSTER, "Kevin", "Mullin", "CA15") == "M001225"
    assert matching.house(ROSTER, "Robert", "Smith", "TX09") == "S000002"      # the district breaks the tie
    assert matching.house(ROSTER, "Nobody", "Here", "TX09") is None
    assert matching.senate(ROSTER, "Markwayne", "Mullin") == "M001190"          # a former senator still matches
    assert matching.senate(ROSTER, "James Conley", "Justice, II") == "J000312"
