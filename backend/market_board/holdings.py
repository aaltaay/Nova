"""State Street's daily SPDR holdings files (ADR 053): who is in each sector, and each sector's biggest names.

The file is an .xlsx (a zip of XML); it is read with the standard library: the row whose cells name ``Ticker`` and
``Weight`` heads the table, the ``Holdings:`` row's "As of DD-Mon-YYYY" dates it. A ticker State Street writes with
a dot (``BRK.B``) is IBKR's with a space (``BRK B``). Rows without a listed ticker (cash, futures) are left out.
Parsed files are kept as ``holdings-<ETF>.json`` (``disk``).
"""
from __future__ import annotations

import io
import re
import time
import zipfile
from datetime import datetime
from typing import Any
from xml.etree import ElementTree as ET

from constants_market_board import (
    MARKET_HOLDINGS_MAX_BYTES,
    MARKET_HOLDINGS_URL,
    MARKET_HTTP_TIMEOUT_SEC,
)
from market_board import disk
from market_board.state import Stated

SOURCE = "ssga"
_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_TICKER = re.compile(r"^[A-Z]{1,5}([ .][A-Z])?$")
_COL = re.compile(r"^([A-Z]+)")


class HoldingsError(Stated):
    """The file could not be fetched or read; the page states it."""


def _shared_strings(z: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t")) for si in root.findall("m:si", _NS)]


def _rows(data: bytes) -> list[dict[str, Any]]:
    """Each sheet row as ``{column letter: value}`` (strings resolved, numbers as float)."""
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        strings = _shared_strings(z)
        sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        raise HoldingsError(f"not a holdings workbook ({type(exc).__name__})") from exc
    out = []
    for row in sheet.iter(f"{{{_NS['m']}}}row"):
        cells: dict[str, Any] = {}
        for c in row.findall("m:c", _NS):
            col = _COL.match(c.get("r") or "")
            if not col:
                continue
            kind = c.get("t")
            v = c.find("m:v", _NS)
            if kind == "s" and v is not None and v.text is not None:
                idx = int(v.text)
                cells[col.group(1)] = strings[idx] if 0 <= idx < len(strings) else None
            elif kind == "inlineStr":
                cells[col.group(1)] = "".join(t.text or "" for t in c.iter(f"{{{_NS['m']}}}t"))
            elif v is not None and v.text is not None:
                try:
                    cells[col.group(1)] = float(v.text)
                except ValueError:
                    cells[col.group(1)] = v.text
        out.append(cells)
    return out


def _as_of(rows: list[dict[str, Any]]) -> str | None:
    for cells in rows[:6]:
        for value in cells.values():
            m = re.search(r"As of (\d{1,2}-[A-Za-z]{3}-\d{4})", str(value or ""))
            if m:
                return datetime.strptime(m.group(1), "%d-%b-%Y").date().isoformat()
    return None


def parse(data: bytes) -> dict[str, Any]:
    """``{as_of, rows: [{symbol, name, weight_pct}]}`` heaviest first."""
    rows = _rows(data)
    header = None
    for i, cells in enumerate(rows):
        names = {str(v).strip().lower(): k for k, v in cells.items() if isinstance(v, str)}
        if "ticker" in names and "weight" in names:
            header = (i, names["ticker"], names["weight"], names.get("name"))
            break
    if header is None:
        raise HoldingsError("no Ticker / Weight header in the file")
    start, tcol, wcol, ncol = header
    out = []
    for cells in rows[start + 1:]:
        ticker = str(cells.get(tcol) or "").strip().upper()
        weight = cells.get(wcol)
        if not _TICKER.match(ticker) or not isinstance(weight, float):
            continue
        out.append({"symbol": ticker.replace(".", " "), "name": (str(cells.get(ncol) or "").strip() or None)
                    if ncol else None, "weight_pct": round(weight, 4)})
    if not out:
        raise HoldingsError("the file lists no holdings")
    out.sort(key=lambda r: r["weight_pct"], reverse=True)
    return {"as_of": _as_of(rows), "rows": out}


def fetch(etf: str) -> dict[str, Any]:
    """Download, parse and keep ``etf``'s file; raises ``HoldingsError`` with the reason."""
    import requests

    from constants_market_board import MARKET_HTTP_USER_AGENT

    url = MARKET_HOLDINGS_URL.format(ticker=etf.lower())
    try:
        resp = requests.get(url, timeout=MARKET_HTTP_TIMEOUT_SEC, headers={"User-Agent": MARKET_HTTP_USER_AGENT},
                            allow_redirects=True)
    except requests.RequestException as exc:
        raise HoldingsError(f"{type(exc).__name__}") from exc
    if resp.status_code != 200:
        raise HoldingsError(f"HTTP {resp.status_code}")
    if len(resp.content) > MARKET_HOLDINGS_MAX_BYTES:
        raise HoldingsError("file larger than expected")
    parsed = parse(resp.content)
    payload = {"etf": etf, "as_of": parsed["as_of"], "fetched_at": time.time(), "rows": parsed["rows"]}
    disk.write(f"holdings-{etf}.json", payload)
    return payload


def cached(etf: str) -> dict[str, Any] | None:
    return disk.read(f"holdings-{etf}.json")


def usable(etf: str, now: float) -> dict[str, Any] | None:
    """The kept file while it is younger than ``MARKET_HOLDINGS_MAX_AGE_SEC``; older is unknown, never stale members."""
    from constants_market_board import MARKET_HOLDINGS_MAX_AGE_SEC

    got = cached(etf)
    if got is None or now - float(got.get("fetched_at") or 0) > MARKET_HOLDINGS_MAX_AGE_SEC:
        return None
    return got
