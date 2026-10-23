"""What the Congress page knows right now (ADR 066): each source's status and the reports and trades read so far.

The reader (``refresh``) writes here; the routes read from here and never wait on a site or the database. ``Book``
holds the reports and their rows as filed and rebuilds the derived trades (``congress.trades.build``) when they
change; ``version`` moves on every change, so the board can keep its last composition until something new is read.
"""
from __future__ import annotations

import threading
from dataclasses import asdict, dataclass

from congress import trades as trade_rules
from congress.constants_congress import CONGRESS_PHOTO_SOURCE


@dataclass
class Source:
    id: str
    name: str
    url: str
    state: str = "waiting"          # off | needs_consent | waiting | reading | ok | failing
    read_at: float | None = None
    next_at: float | None = None
    error: str | None = None
    done: int = 0                   # while reading: reports read in this pass
    todo: int = 0                   # while reading: reports in this pass

    def wire(self, counts: dict | None = None) -> dict:
        return {**asdict(self), **(counts or {})}


class Book:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.version = 0
        self.loaded = False
        self._reports: dict[str, dict] = {}
        self._rows: dict[str, list[dict]] = {}
        self._trades: list[trade_rules.Trade] = []

    def replace(self, reports: dict[str, dict], rows: dict[str, list[dict]]) -> None:
        with self._lock:
            self._reports, self._rows = dict(reports), {k: list(v) for k, v in rows.items()}
            self._rebuild()
            self.loaded = True

    def put(self, report: dict, rows: list[dict] | None) -> None:
        with self._lock:
            self._reports[report["id"]] = dict(report)
            if rows is not None:
                self._rows[report["id"]] = list(rows)
            self._rebuild()

    def set_fields(self, report_id: str, **fields) -> None:
        with self._lock:
            if report_id in self._reports:
                self._reports[report_id].update(fields)
                self._rebuild()

    def _rebuild(self) -> None:
        out = []
        for rid, report in self._reports.items():
            if report.get("amended_by"):
                continue                        # a later amendment's rows stand for this report's
            for n, row in enumerate(self._rows.get(rid, ())):
                out.append(trade_rules.build({**report, "filed": report.get("amends") or report["filed"]},
                                             {**row, "n": n}))
        out.sort(key=lambda t: (t.filed, t.tx), reverse=True)
        self._trades = out
        self.version += 1

    def snapshot(self) -> tuple[int, dict[str, dict], list[trade_rules.Trade]]:
        with self._lock:
            return self.version, dict(self._reports), list(self._trades)

    def report(self, report_id: str) -> dict | None:
        with self._lock:
            r = self._reports.get(report_id)
            return dict(r) if r else None

    def reset(self) -> None:
        with self._lock:
            self._reports, self._rows, self._trades = {}, {}, []
            self.version += 1
            self.loaded = False


SOURCES = {
    "house": ("House Clerk", "https://disclosures-clerk.house.gov/FinancialDisclosure"),
    "senate": ("Senate eFD", "https://efdsearch.senate.gov/search/"),
    "roster": ("Members (unitedstates/congress-legislators)", "https://github.com/unitedstates/congress-legislators"),
    "photos": ("Official portraits (Biographical Directory of the U.S. Congress)", CONGRESS_PHOTO_SOURCE),
}

_lock = threading.Lock()
_sources: dict[str, Source] = {}
_book = Book()


def source(key: str) -> Source:
    with _lock:
        if key not in _sources:
            name, url = SOURCES[key]
            _sources[key] = Source(key, name, url)
        return _sources[key]


def sources() -> list[Source]:
    return [source(k) for k in SOURCES]


def book() -> Book:
    return _book


def reset_for_tests() -> None:
    with _lock:
        _sources.clear()
    _book.reset()
