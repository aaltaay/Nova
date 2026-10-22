"""ADR 066: reading a House Periodic Transaction Report's text (congress/house_pdf.py).

The fixtures copy the shape pypdf gives the Clerk's e-filed PDFs (names invented): section labels whose letters
extract as NUL, a type run against the asset, a page break inside a record, an amended report's transaction IDs.
"""
import pytest

from congress.house_pdf import PdfUnreadable, parse_text, pdf_text

HEAD = (
    "P\x00\x00\x00 T\x00\x00\x00 R\x00\x00\x00\n"
    "Clerk of the House of Representatives • Legislative Resource Center • B81 Cannon Building\n"
    "F\x00\x00\x00\x00 I\x00\x00\x00\nName: Hon. Pat Example\nStatus: Member\nState/District:XX07\nT\x00\x00\x00\n"
)
COLUMNS = "ID Owner Asset Transaction\nType\nDate Notification\nDate\nAmount Cap.\nGains >\n$200?\n"
TAIL = ("* For the complete list of asset type abbreviations, please visit https://fd.house.gov/reference/.\n"
        "I CERTIFY that the statements I have made ...\nDigitally Signed: Hon. Pat Example , 06/23/2026\n"
        "Filing ID #20099999\n")


def report(body: str) -> str:
    return HEAD + COLUMNS + body + TAIL


def test_a_spouse_option_and_a_wrapped_amount():
    rows = parse_text(report(
        "SP Example Corp - Common Stock\n(EXMP) [OP]\nP 05/29/202605/29/2026$1,000,001 -\n$5,000,000\n"
        "F\x00\x00\x00\x00\x00 S\x00\x00\x00\x00\x00: New\n"
        "D\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00: Purchased 200 call options with a strike price of $50 and an "
        "expiration date of 3/19/27.\n"))
    assert len(rows) == 1
    r = rows[0]
    assert (r.owner, r.ticker, r.asset_type, r.tx_type) == ("spouse", "EXMP", "OP", "P")
    assert (r.tx_date, r.notified) == ("2026-05-29", "2026-05-29")
    assert r.amount == "$1,000,001 - $5,000,000"
    assert r.asset == "Example Corp - Common Stock"
    assert r.status == "New"
    assert r.description.startswith("Purchased 200 call options") and r.description.endswith("3/19/27.")


def test_types_run_against_the_asset_and_the_tag():
    rows = parse_text(report(
        "Example Holdings, PLC OrdinaryP 01/30/202602/11/2026$1,001 - $15,000\n"
        "F S : New\n"
        "JT King County Example 4.00% 12/01/32 [GS]E 07/26/202608/01/2026$15,001 -\n$50,000\n"
        "F S : New\nS O : Stocks, Bonds, & Mutual Funds\nD : Called Security, $35,000\n"))
    assert [(r.tx_type, r.owner, r.asset_type, r.amount) for r in rows] == [
        ("P", "self", None, "$1,001 - $15,000"),
        ("E", "joint", "GS", "$15,001 - $50,000"),
    ]
    assert rows[0].asset == "Example Holdings, PLC Ordinary"
    assert rows[1].subholding == "Stocks, Bonds, & Mutual Funds"
    assert rows[1].description == "Called Security, $35,000"


def test_a_page_break_inside_a_record_keeps_its_ticker_and_amount():
    rows = parse_text(report(
        "Franco Example Corporation (FEX)P 01/27/202602/11/2026$15,001 -\n"
        "Filing ID #20099999\n" + COLUMNS + "[ST] $50,000\nF S : New\n"
        "Example Communications Corporation -S (partial) 12/19/202501/09/2026$1,001 - $15,000\n"
        "Filing ID #20099999\n" + COLUMNS + "Class A Common Stock (EXCO) [ST]\nF S : New\n"))
    assert [(r.ticker, r.asset_type, r.tx_type, r.amount) for r in rows] == [
        ("FEX", "ST", "P", "$15,001 - $50,000"),
        ("EXCO", "ST", "S (partial)", "$1,001 - $15,000"),
    ]
    assert rows[1].asset == "Example Communications Corporation - Class A Common Stock"


def test_descriptions_wrap_and_cross_page_breaks():
    rows = parse_text(report(
        "SP Example One - Common Stock\n(ONE) [ST]\nP 01/16/202601/16/2026$500,001 -\n$1,000,000\nF S : New\n"
        "D : Exercised 50 call options purchased 1/14/25 (5,000 shares) at a strike price of $150 with an "
        "expiration date of\n1/16/26.\n"
        "SP Example Two - Common Stock\n(TWO) [ST]\nS (partial) 12/24/202512/24/2025$1,000,001 -\n$5,000,000\n"
        "F S : New\nFiling ID #20099999\n" + COLUMNS + "D : Sold 20,000 shares.\n"
        "Example Three, Inc.\n(THR) [ST]\nP 01/09/202601/12/2026$1,001 - $15,000\nF S : New\n"))
    assert [r.ticker for r in rows] == ["ONE", "TWO", "THR"]
    assert rows[0].description.endswith("expiration date of 1/16/26.")
    assert rows[1].description == "Sold 20,000 shares."
    assert rows[2].asset == "Example Three, Inc." and rows[2].description == ""


def test_an_amended_report_puts_transaction_ids_before_the_owner():
    rows = parse_text(report(
        "2000076739SP Example Pay Holdings, Inc. (EXPY) [ST] P 02/10/202102/15/2021 $1,001 - $15,000\n"
        "F S : Amended\nS O : LIVTR\n"
        "2000166537JT Example Organon & Co. Common Stock\n(EXOR) [ST]\nS 08/05/202608/05/2026$1,001 - $15,000\n"
        "F S : Amended\n"))
    assert [(r.owner, r.ticker, r.status) for r in rows] == [("spouse", "EXPY", "Amended"), ("joint", "EXOR", "Amended")]
    assert rows[0].asset == "Example Pay Holdings, Inc."


def test_a_ticker_counts_only_before_its_type_tag():
    rows = parse_text(report(
        "Advanced Example Intelligence (AEI)\nLabs [OI]\nP 01/29/202601/29/2026$15,001 -\n$50,000\n"
        "F S : New\nD : World Model AI, Paris, France\n"))
    assert rows[0].ticker is None and rows[0].asset_type == "OI"
    assert rows[0].asset == "Advanced Example Intelligence (AEI) Labs"


def test_nothing_after_the_closing_sections_is_read():
    text = report("Example Corp (EXC) [ST]\nP 01/02/202601/05/2026$1,001 - $15,000\nF S : New\n")
    text += "P 01/02/202601/05/2026$1,001 - $15,000\n"         # past the closing sections: never a row
    assert len(parse_text(text)) == 1


def test_a_broken_pdf_is_unreadable():
    with pytest.raises(PdfUnreadable):
        pdf_text(b"%PDF-1.7 not really a pdf")
