"""The House Clerk's reports (ADR 066): the yearly index, then each e-filed report's PDF.

``sync_index`` asks for a year's ``<YEAR>FD.zip`` (with ``If-Modified-Since``) and lists every Periodic Transaction
Report in it as a report record -- a scanned paper one (DocID 8... / 9...) as ``kind: "paper"``, never downloaded.
``read`` downloads one e-filed PDF and reads its rows (``house_pdf``). Records carry the filer as the index names them
and the member they match; nothing here decides what the page shows.
"""
from __future__ import annotations

import csv
import io
import logging
import zipfile
from datetime import datetime

from congress import house_pdf, matching
from congress.constants_congress import (
    CONGRESS_HOUSE_INDEX_URL,
    CONGRESS_HOUSE_PAPER_PREFIXES,
    CONGRESS_HOUSE_PDF_URL,
    CONGRESS_MAX_PDF_BYTES,
    CONGRESS_PARSER_VERSION,
)

logger = logging.getLogger(__name__)
PARSER = CONGRESS_PARSER_VERSION["house"]


def index_rows(zip_bytes: bytes, year: int) -> list[dict]:
    """The PTR lines of a year's index ZIP: ``{doc, first, last, state_dst, filed}`` (``filed`` as YYYY-MM-DD)."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        name = next((n for n in z.namelist() if n.lower() == f"{year}fd.txt"), None)
        if name is None:
            raise ValueError(f"the {year} index has no {year}FD.txt")
        text = z.read(name).decode("utf-8-sig", errors="replace")
    out = []
    for r in csv.DictReader(io.StringIO(text), delimiter="\t"):
        doc = (r.get("DocID") or "").strip()
        if (r.get("FilingType") or "").strip() != "P" or not doc.isdigit():
            continue
        try:
            filed = datetime.strptime((r.get("FilingDate") or "").strip(), "%m/%d/%Y").date().isoformat()
        except ValueError:
            continue
        out.append({"doc": doc, "first": (r.get("First") or "").strip(), "last": (r.get("Last") or "").strip(),
                    "state_dst": (r.get("StateDst") or "").strip(), "filed": filed})
    return out


def record(row: dict, year: int, members: list[dict]) -> dict:
    """A report record for one index line (not yet read)."""
    paper = row["doc"].startswith(CONGRESS_HOUSE_PAPER_PREFIXES)
    first, last = row["first"], row["last"]
    return {"id": f"H:{year}:{row['doc']}", "chamber": "house", "filer_name": f"{first} {last}".strip(),
            "filer_first": first, "filer_last": last, "filer_state": row["state_dst"][:2],
            "filer_district": row["state_dst"][2:] or None,
            "bioguide": matching.house(members, first, last, row["state_dst"]), "filed": row["filed"],
            "kind": "paper" if paper else "electronic",
            "url": CONGRESS_HOUSE_PDF_URL.format(year=year, doc=row["doc"]), "title": None, "amends": None,
            "amended_by": None, "parser": None, "read_at": None, "error": None, "trades": 0}


def sync_index(net, store, year: int, members: list[dict], known: set[str]) -> list[dict]:
    """New report records from a year's index (none when the Clerk has not rebuilt it since the last read)."""
    key = f"house:{year}:modified"
    since = store.meta(key)
    resp = net.get(CONGRESS_HOUSE_INDEX_URL.format(year=year), headers={"If-Modified-Since": since} if since else None)
    if resp.status_code == 304:
        return []
    if resp.status_code == 404:
        return []                               # a year the Clerk has no index for yet (early January)
    resp.raise_for_status()
    rows = index_rows(resp.content, year)
    fresh = [record(r, year, members) for r in rows if f"H:{year}:{r['doc']}" not in known]
    if resp.headers.get("Last-Modified"):
        store.set_meta(key, resp.headers["Last-Modified"])
    return fresh


def pending(report: dict) -> bool:
    """An e-filed report not yet read by this parser."""
    return report["chamber"] == "house" and report["kind"] == "electronic" and report.get("parser") != PARSER


def read(net, report: dict, now: float) -> tuple[dict, list[dict] | None]:
    """Download and read one e-filed report: (the updated record, its rows or None when it could not be read)."""
    resp = net.get(report["url"], max_bytes=CONGRESS_MAX_PDF_BYTES)
    if resp.status_code != 200:
        return {**report, "error": f"the Clerk answered HTTP {resp.status_code}"}, None
    try:
        rows = house_pdf.parse_text(house_pdf.pdf_text(resp.content))
    except house_pdf.PdfLibraryMissing as exc:
        return {**report, "error": str(exc)}, None      # read again once pypdf is installed
    except house_pdf.PdfUnreadable as exc:
        return {**report, "parser": PARSER, "read_at": now, "error": str(exc)}, []
    return ({**report, "parser": PARSER, "read_at": now, "error": None},
            [{"tx": r.tx_date, "notified": r.notified, "owner": r.owner, "ticker": r.ticker, "asset": r.asset,
              "asset_type": r.asset_type, "tx_type": r.tx_type, "amount": r.amount, "status": r.status,
              "subholding": r.subholding, "description": r.description} for r in rows])
