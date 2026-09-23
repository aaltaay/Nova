"""Parse IBKR's short-stock availability file (``usa.txt``). Pure: no I/O, no clock.

The file is ``#BOF|YYYY.MM.DD|HH:MM:SS`` (US Eastern), a ``#SYM|CUR|NAME|CON|ISIN|REBATERATE|FEERATE|
AVAILABLE|FIGI|`` header, one row per symbol and ``#EOF|<rows>``. Fees and rebates are annual percent;
AVAILABLE is shares IBKR can lend, written ``>10000000`` above ten million. A share class is written with
a space (``BRK B``); the desk writes it with a slash (``BRK/B``). Only USD rows are kept.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from constants_move_reason import MOVE_BORROW_CAPPED_SHARES, MOVE_BORROW_CURRENCY

ET = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class BorrowRow:
    fee_rate: float | None
    rebate_rate: float | None
    available: int | None
    capped: bool          # AVAILABLE was ">10000000": at least that many


@dataclass(frozen=True)
class BorrowFile:
    file_ts: float | None           # the file's own timestamp (#BOF), None when missing or unreadable
    rows: dict[str, BorrowRow]
    complete: bool                  # the #EOF count matched the rows read


def desk_symbol(raw: str) -> str:
    return " ".join(raw.split()).upper().replace(" ", "/")


def _num(text: str) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _available(text: str) -> tuple[int | None, bool]:
    t = (text or "").strip()
    if t.startswith(">"):
        return MOVE_BORROW_CAPPED_SHARES, True
    value = _num(t)
    return (int(value), False) if value is not None else (None, False)


def parse(text: str | bytes) -> BorrowFile:
    if isinstance(text, (bytes, bytearray)):
        text = bytes(text).decode("utf-8", "replace")
    file_ts: float | None = None
    rows: dict[str, BorrowRow] = {}
    eof_count: int | None = None
    seen = 0
    for line in text.splitlines():
        parts = line.rstrip().split("|")
        if not parts or not parts[0]:
            continue
        tag = parts[0]
        if tag == "#BOF" and len(parts) >= 3:
            try:
                file_ts = datetime.strptime(f"{parts[1]} {parts[2]}", "%Y.%m.%d %H:%M:%S").replace(tzinfo=ET).timestamp()
            except ValueError:
                file_ts = None
            continue
        if tag == "#EOF":
            eof_count = int(_num(parts[1]) or 0) if len(parts) > 1 else None
            continue
        if tag.startswith("#") or len(parts) < 8:
            continue
        seen += 1
        if parts[1].strip().upper() != MOVE_BORROW_CURRENCY:
            continue
        available, capped = _available(parts[7])
        rows[desk_symbol(tag)] = BorrowRow(fee_rate=_num(parts[6]), rebate_rate=_num(parts[5]),
                                           available=available, capped=capped)
    return BorrowFile(file_ts=file_ts, rows=rows, complete=eof_count is not None and eof_count == seen)
