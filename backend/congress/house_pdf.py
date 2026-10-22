"""A House Periodic Transaction Report, read from its PDF (ADR 066). Pure: bytes or text in, rows out.

The Clerk's e-filed PTRs are generated PDFs. pypdf's plain text gives one record per transaction, in this order
(architecture/schema/congress.md, "Reading a House report"):

    SP Apple Inc. - Common Stock (AAPL)        <- the asset: owner code (SP / JT / DC, none for the member's own;
    [ST]                                          an amended report may put a transaction ID first), the asset as
                                                  filed, its ticker and its type tag
    S (partial) 12/24/202512/24/2025$5,000,001 -   <- type, transaction date, notification date, amount; the type may
    $25,000,000                                       sit against the asset's last character ("OrdinaryP 01/30/...")
    F      S     : New                             <- filing status (New / Amended); every record has one
    S          O : 150 Main Street Trust           <- subholding of (optional)
    D          : Sold 45,000 shares.               <- the filer's own words (optional, may wrap)

A page break repeats the column header anywhere -- even inside a record, so the rest of an asset or the amount's
upper bound can follow the transaction line. Lines between a transaction line and its first field line belong to that
record. The section labels' letters extract as NUL and are read as spaces. Nothing is guessed: a field the report
does not hold is None.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

TX = re.compile(r"(P|S \(partial\)|S|E)\s+(\d{2}/\d{2}/\d{4})\s*(\d{2}/\d{2}/\d{4})\s*(.*)$")
FIELD = re.compile(r"^([A-Z])(?:\s+([A-Z]))?\s+:\s?(.*)$")
TICKER_TAG = re.compile(r"\(([A-Z][A-Z0-9.\-/]{0,9})\)\s*\[([A-Z]{2})\]")
TAG = re.compile(r"\[([A-Z]{2})\]")
TICKER = re.compile(r"\([A-Z][A-Z0-9.\-/]{0,9}\)")
MONEY = re.compile(r"\$[\d,]+")
TX_ID = re.compile(r"^\d{6,}\s*")
OWNERS = {"SP": "spouse", "JT": "joint", "DC": "child"}
HEADER_FIRST = "ID Owner Asset Transaction"
HEADER_LAST = "$200?"
END_MARKS = ("* For the complete list of asset type abbreviations", "I CERTIFY")
FULL_STOP = (".", ".)", '."')
MAX_WRAP_LINES = 3


class PdfUnreadable(Exception):
    """The PDF could not be opened or holds no transaction text; the reader lists the report unread, with this reason."""


class PdfLibraryMissing(PdfUnreadable):
    """pypdf is not installed: every report waits (read again once it is), none is marked unreadable."""


@dataclass
class HouseRow:
    owner: str                  # "self" | "spouse" | "joint" | "child"
    asset: str                  # the asset as filed, without owner code, ticker or tag
    ticker: str | None
    asset_type: str | None      # the Clerk's two-letter code: ST stock, OP option, GS government security, ...
    tx_type: str                # "P" | "S" | "S (partial)" | "E"
    tx_date: str                # YYYY-MM-DD
    notified: str               # YYYY-MM-DD
    amount: str                 # as filed: "$1,001 - $15,000", "Spouse/DC Over $1,000,000", ...
    status: str | None = None   # "New" | "Amended"
    subholding: str | None = None
    description: str = ""
    raw_asset: str = field(default="", repr=False)


def pdf_text(data: bytes) -> str:
    """Every page's plain text, joined. Raises PdfUnreadable for a broken PDF or one with no transaction text."""
    try:
        import pypdf  # backend/requirements.txt; imported here so a desk without it states the reason
    except ImportError as exc:
        raise PdfLibraryMissing("the pypdf package is not installed (pip install -r backend/requirements.txt)") from exc
    try:
        reader = pypdf.PdfReader(io.BytesIO(data))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as exc:  # noqa: BLE001 -- a broken PDF is one unreadable report, never a crash
        raise PdfUnreadable(f"the PDF could not be read ({type(exc).__name__})") from exc
    if not any(TX.search(line) for line in _body(text)):
        raise PdfUnreadable("the PDF holds no transaction text")
    return text


def _iso(us: str) -> str:
    m, d, y = us.split("/")
    return f"{y}-{m}-{d}"


def _body(text: str) -> list[str]:
    """The transaction lines: after the first column header, before the closing sections; repeated page headers and
    the 'Filing ID' footers dropped, NUL letters read as spaces, runs of spaces as one."""
    out: list[str] = []
    started = skipping = False
    for raw in text.replace("\x00", " ").splitlines():
        line = " ".join(raw.split())
        if not line:
            continue
        if line.startswith(END_MARKS):
            break
        if line.startswith(HEADER_FIRST):
            started = skipping = True
            continue
        if skipping:
            skipping = line != HEADER_LAST
            continue
        if started and not line.startswith("Filing ID #"):
            out.append(line)
    return out


def _open(description: str) -> bool:
    """A description that has not ended its sentence (its wrap may follow on the next lines)."""
    return bool(description) and not description.endswith(FULL_STOP)


def _split_run(run: list[str], open_description: bool) -> tuple[list[str], list[str]]:
    """Split the lines before a transaction into (the last record's description wrap, this record's asset).

    An owner code (or a transaction ID) always starts an asset. Otherwise a wrap is taken only while the last
    description is unfinished, only from lines without a ticker or type tag, up to the first that ends its sentence."""
    start = next((i for i, line in enumerate(run) if _owner_code(line)), None)
    if start is not None:
        return (run[:start] if open_description else []), run[start:]
    if not open_description:
        return [], run
    for k in range(min(MAX_WRAP_LINES, len(run) - 1)):
        if TICKER.search(run[k]) or TAG.search(run[k]):
            break
        if run[k].endswith(FULL_STOP):
            return run[: k + 1], run[k + 1:]
    return [], run


def _owner_code(line: str) -> str | None:
    first = TX_ID.sub("", line).split(" ", 1)[0]
    return first if first in OWNERS else None


def parse_text(text: str) -> list[HouseRow]:
    """Every transaction row of a House PTR's plain text, in the report's order."""
    body = _body(text)
    rows: list[HouseRow] = []
    region_start = 0
    for i, line in enumerate(body):
        m = TX.search(line)
        if not m:
            continue
        run = _close(rows[-1], body[region_start:i]) if rows else body[region_start:i]
        same_line = line[: m.start()].strip()
        wrap, asset = _split_run(run + ([same_line] if same_line else []), bool(rows) and _open(rows[-1].description))
        if wrap:
            rows[-1].description = " ".join([rows[-1].description, *wrap])
        row = HouseRow(owner="self", asset="", ticker=None, asset_type=None, tx_type=m.group(1),
                       tx_date=_iso(m.group(2)), notified=_iso(m.group(3)), amount=m.group(4).strip())
        _set_asset(row, " ".join(asset))
        rows.append(row)
        region_start = i + 1
    if rows:
        rest = _close(rows[-1], body[region_start:])
        if rest and _open(rows[-1].description):
            rows[-1].description = " ".join([rows[-1].description, *rest[:MAX_WRAP_LINES]])
    return rows


def _close(row: HouseRow, region: list[str]) -> list[str]:
    """Give `row` what follows its transaction line -- the rest of its asset or amount after a page break, then its
    field lines and description -- and return the lines after its last field line (the next record's asset run)."""
    first = next((k for k, line in enumerate(region) if FIELD.match(line)), None)
    if first is None:                     # no field line: everything belongs to the next record
        return region
    after = region[:first]
    if row.amount.endswith("-"):
        for k, piece in enumerate(after):
            money = MONEY.search(piece)
            if money:
                row.amount = f"{row.amount} {money.group(0)}"
                after[k] = (piece[: money.start()] + piece[money.end():]).strip()
                break
    extra = " ".join(p for p in after if p)
    if extra:
        _set_asset(row, f"{row.raw_asset} {extra}")
    last = max(k for k, line in enumerate(region) if FIELD.match(line))
    _fields(row, region[first: last + 1])
    return region[last + 1:]


def _fields(row: HouseRow, lines: list[str]) -> None:
    """A record's filing status, subholding and description, from its field lines (a description may wrap)."""
    current = None
    for line in lines:
        m = FIELD.match(line)
        if not m:
            if current == "D":
                row.description = f"{row.description} {line}".strip()
            continue
        label, second, value = m.group(1), m.group(2), m.group(3).strip()
        current = None
        if (label, second) == ("F", "S"):
            row.status = value or None
        elif (label, second) == ("S", "O"):
            row.subholding = value or None
        elif label == "D" and second is None:
            row.description, current = value, "D"


def _set_asset(row: HouseRow, raw: str) -> None:
    """Owner, asset name, ticker and type tag from the asset's text (all of it read so far)."""
    row.raw_asset = raw.strip()
    text = TX_ID.sub("", row.raw_asset)
    code = text.split(" ", 1)[0] if text else ""
    row.owner = OWNERS.get(code, "self")
    if code in OWNERS:
        text = text[len(code):].strip()
    pairs = list(TICKER_TAG.finditer(text))
    if pairs:
        row.ticker, row.asset_type = pairs[-1].group(1), pairs[-1].group(2)
        name = text[: pairs[-1].start()]
    else:
        tags = list(TAG.finditer(text))
        row.ticker, row.asset_type = None, (tags[-1].group(1) if tags else None)
        name = text[: tags[-1].start()] if tags else text
    row.asset = name.strip().rstrip(" -").strip()
