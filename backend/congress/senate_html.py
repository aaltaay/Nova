"""A Senate Periodic Transaction Report, read from eFD's own pages (ADR 066). Pure: text in, rows out.

``search_row`` reads one row of eFD's report search; ``parse_report`` reads an e-filed report's transaction table
(architecture/schema/congress.md, "Reading a Senate report"). A paper report is an image: listed, never read here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape

HREF = re.compile(r'href="([^"]+)"')
TAG = re.compile(r"<[^>]+>")
TITLE_DATE = re.compile(r"for (\d{2}/\d{2}/\d{4})")
AMENDMENT = re.compile(r"\(Amendment\s*\d*\)", re.I)
REPORT_ID = re.compile(r"/search/view/(ptr|paper)/([0-9a-fA-F-]{8,})/")
TBODY = re.compile(r"<tbody[^>]*>(.*?)</tbody>", re.S | re.I)
ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)


@dataclass
class SenateReport:
    id: str                     # "S:<uuid>"
    url: str
    kind: str                   # "electronic" | "paper"
    first: str
    last: str
    filer: str                  # "Last, First (Senator)" as eFD lists it
    filed: str                  # YYYY-MM-DD: the day eFD received it
    title: str
    report_date: str | None     # YYYY-MM-DD in its title: an amendment's is the report it corrects
    amendment: bool


@dataclass
class SenateRow:
    tx_date: str                # YYYY-MM-DD
    owner: str                  # as filed: Self / Spouse / Joint / Child
    ticker: str | None
    asset: str
    asset_type: str
    tx_type: str                # Purchase / Sale (Full) / Sale (Partial) / Exchange
    amount: str
    comment: str


def _text(html: str) -> str:
    return " ".join(unescape(TAG.sub(" ", html)).split())


def _iso(us: str) -> str:
    m, d, y = us.strip().split("/")
    return f"{y}-{int(m):02d}-{int(d):02d}"


def search_row(row: list, base: str) -> SenateReport | None:
    """One row of eFD's search answer: ``[first, last, "Last, First (Senator)", "<a href=...>Title</a>", "MM/DD/YYYY"]``.
    None for a row that does not have that shape."""
    if not isinstance(row, list) or len(row) < 5:
        return None
    first, last, full, link, filed = (str(x) for x in row[:5])
    href = HREF.search(link)
    rid = REPORT_ID.search(href.group(1)) if href else None
    if not rid:
        return None
    title = _text(link)
    date = TITLE_DATE.search(title)
    try:
        filed_iso = _iso(filed)
        report_date = _iso(date.group(1)) if date else None
    except ValueError:
        return None
    return SenateReport(id=f"S:{rid.group(2).lower()}", url=base + href.group(1), first=_text(first),
                        last=_text(last), filer=_text(full), filed=filed_iso, title=title, report_date=report_date,
                        amendment=bool(AMENDMENT.search(title)),
                        kind="electronic" if rid.group(1) == "ptr" else "paper")


def parse_report(html: str) -> list[SenateRow] | None:
    """The transactions of an e-filed report page, in its order; None when the page has no transaction table."""
    body = TBODY.search(html)
    if not body:
        return None
    rows: list[SenateRow] = []
    for tr in ROW.findall(body.group(1)):
        cells = [_text(c) for c in CELL.findall(tr)]
        if len(cells) < 9:
            continue
        _, tx, owner, ticker, asset, asset_type, tx_type, amount, comment = cells[:9]
        try:
            tx_iso = _iso(tx)
        except ValueError:
            continue
        rows.append(SenateRow(tx_date=tx_iso, owner=owner, ticker=None if ticker in ("", "--") else ticker,
                              asset=asset, asset_type=asset_type, tx_type=tx_type, amount=amount,
                              comment="" if comment in ("", "--") else comment))
    return rows
