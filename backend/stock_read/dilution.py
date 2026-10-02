"""Dilution on file (ADR 036, the ``float`` group): what SEC EDGAR lists for the symbol's registrant. Pure.

Four kinds of filing, read from the registrant's submissions file
(``data.sec.gov/submissions/CIK##########.json``: the columns ``form``, ``filingDate`` and ``items``):

  shelf        an S-3 / F-3 family registration filed within ``STOCK_READ_DILUTION_SHELF_DAYS``
  prospectus   any 424B* filed within ``STOCK_READ_DILUTION_PROSPECTUS_DAYS``
  s1           an S-1 / F-1 family registration filed within ``STOCK_READ_DILUTION_S1_DAYS``
  placement    an 8-K whose Items include 3.02 filed within ``STOCK_READ_DILUTION_PLACEMENT_DAYS``

``digest`` reduces what was fetched to the filings that can matter and how far back the list was read,
``flags`` judges them at a date, and ``row`` words the reader's answer (``stock_read/dilution_reader.py``)
as the read's row. A kind is "none on file" only when the list was read back to the start of its window:
EDGAR pages a long list, and a page nobody read is unknown, never clean.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from constants_stock_read import (
    STOCK_READ_DILUTION_ENV,
    STOCK_READ_DILUTION_KEEP_PER_KIND,
    STOCK_READ_DILUTION_MAX_PAGES,
    STOCK_READ_DILUTION_PAGE_NAME_RE,
    STOCK_READ_DILUTION_PLACEMENT_DAYS,
    STOCK_READ_DILUTION_PLACEMENT_FORMS,
    STOCK_READ_DILUTION_PLACEMENT_ITEM,
    STOCK_READ_DILUTION_PROSPECTUS_DAYS,
    STOCK_READ_DILUTION_PROSPECTUS_PREFIX,
    STOCK_READ_DILUTION_S1_DAYS,
    STOCK_READ_DILUTION_S1_FORMS,
    STOCK_READ_DILUTION_SHELF_DAYS,
    STOCK_READ_DILUTION_SHELF_FORMS,
    STOCK_READ_DILUTION_SOURCE,
)

ET = ZoneInfo("America/New_York")
ROW_ID = "dilution_on_file"
ROW_LABEL = "Dilution on file"
KINDS = ("shelf", "prospectus", "s1", "placement")
DAYS = {"shelf": STOCK_READ_DILUTION_SHELF_DAYS, "prospectus": STOCK_READ_DILUTION_PROSPECTUS_DAYS,
        "s1": STOCK_READ_DILUTION_S1_DAYS, "placement": STOCK_READ_DILUTION_PLACEMENT_DAYS}
# What each kind is called: in a sentence about one filing, and when none (or no answer) is on file.
FILED = {"shelf": "Shelf registration", "prospectus": "Prospectus", "s1": "Registration statement",
         "placement": "Unregistered sale of equity"}
ABSENT = {"shelf": "S-3 / F-3 shelf", "prospectus": "424B prospectus", "s1": "S-1 / F-1",
          "placement": "8-K Item 3.02"}
_UNDATED = "9999-12-31"        # a page EDGAR lists without its last date may reach into any window
_PAGE_NAME = re.compile(STOCK_READ_DILUTION_PAGE_NAME_RE)


def today_et(now: float) -> date:
    return datetime.fromtimestamp(float(now), ET).date()


def kind_of(form: str, items: str = "") -> str | None:
    """Which of the four kinds a filing is, by its form (and, for an 8-K, its Items); None for any other."""
    form = (form or "").strip().upper()
    if form in STOCK_READ_DILUTION_SHELF_FORMS:
        return "shelf"
    if form.startswith(STOCK_READ_DILUTION_PROSPECTUS_PREFIX):
        return "prospectus"
    if form in STOCK_READ_DILUTION_S1_FORMS:
        return "s1"
    if form in STOCK_READ_DILUTION_PLACEMENT_FORMS and STOCK_READ_DILUTION_PLACEMENT_ITEM in {
            part.strip() for part in (items or "").split(",")}:
        return "placement"
    return None


def block_rows(block: Any) -> list[dict[str, str]]:
    """The filings of a kind in one columnar block (``recent``, or an older page), as ``{kind, form, date}``.

    A block that is not one, or a filing of a kind without a date, raises: the read then fails and says
    so, instead of answering from a list it could not place in time."""
    forms = block.get("form") if isinstance(block, Mapping) else None
    dates = block.get("filingDate") if isinstance(block, Mapping) else None
    if not isinstance(forms, list) or not isinstance(dates, list) or len(forms) != len(dates):
        raise ValueError("not an EDGAR filings list (no form / filingDate columns)")
    items = block.get("items") if isinstance(block.get("items"), list) else []
    out = []
    for i, form in enumerate(forms):
        kind = kind_of(str(form or ""), str(items[i] or "") if i < len(items) else "")
        if kind is None:
            continue
        try:
            day = date.fromisoformat(str(dates[i]))
        except ValueError:
            raise ValueError(f"EDGAR lists a {form} without a filing date") from None
        out.append({"kind": kind, "form": str(form).strip().upper(), "date": day.isoformat()})
    return out


def _recent(payload: Any) -> Any:
    filings = payload.get("filings") if isinstance(payload, Mapping) else None
    if not isinstance(filings, Mapping) or "recent" not in filings:
        raise ValueError("not an EDGAR submissions file (no filings.recent)")
    return filings["recent"]


def _pages(payload: Mapping[str, Any]) -> list[tuple[str, str]]:
    """The older pages EDGAR lists beside ``recent``: ``(last filing date, file name)``."""
    listed = payload["filings"].get("files")
    return [(str(e.get("filingTo") or _UNDATED), str(e.get("name") or ""))
            for e in (listed if isinstance(listed, list) else []) if isinstance(e, Mapping)]


def _start(kind: str, today: date) -> str:
    return (today - timedelta(days=DAYS[kind])).isoformat()


def flags(filings: list[Mapping[str, Any]], unread_to: str | None, today: date) -> dict[str, dict[str, Any]]:
    """Each kind at ``today``: ``on_file`` (its newest filing and how many), ``none``, or ``unknown`` when
    none was found and filings dated up to ``unread_to`` -- inside its window -- were never read."""
    out: dict[str, dict[str, Any]] = {}
    for kind in KINDS:
        start = _start(kind, today)
        mine = [f for f in filings if f.get("kind") == kind and str(f.get("date") or "") >= start]
        if mine:
            newest = max(mine, key=lambda f: str(f["date"]))
            out[kind] = {"state": "on_file", "form": newest["form"], "date": newest["date"], "count": len(mine)}
        elif unread_to is not None and start <= unread_to:
            out[kind] = {"state": "unknown", "unread_to": unread_to}
        else:
            out[kind] = {"state": "none"}
    return out


def pages_wanted(payload: Any, today: date) -> list[str]:
    """The older pages worth reading, newest first: those that reach into the window of a kind ``recent``
    does not hold. None when more than ``STOCK_READ_DILUTION_MAX_PAGES`` would be needed (or one cannot be
    named): the kind is then stated as not known."""
    found = flags(block_rows(_recent(payload)), None, today)
    missing = [kind for kind in KINDS if found[kind]["state"] != "on_file"]
    if not missing:
        return []
    start = min(_start(kind, today) for kind in missing)
    needed = sorted((p for p in _pages(payload) if p[0] >= start), reverse=True)
    if len(needed) > STOCK_READ_DILUTION_MAX_PAGES or not all(_PAGE_NAME.match(name) for _to, name in needed):
        return []
    return [name for _to, name in needed]


def digest(payload: Any, pages: Mapping[str, Any], today: date) -> dict[str, Any]:
    """What one read of EDGAR found: ``{name, filings, more, unread_to}``.

    ``filings`` are the rows of a kind inside its window at ``today``, newest first, at most
    ``STOCK_READ_DILUTION_KEEP_PER_KIND`` per kind (``more`` names a kind cut there). ``unread_to`` is the
    last filing date of the newest page that was not read (None when every page was): nothing dated on or
    before it is known."""
    rows = block_rows(_recent(payload))
    for page in pages.values():
        rows += block_rows(page)
    unread = [to for to, name in _pages(payload) if name not in pages]
    filings: list[dict[str, str]] = []
    more: list[str] = []
    for kind in KINDS:
        start = _start(kind, today)
        mine = sorted((r for r in rows if r["kind"] == kind and r["date"] >= start),
                      key=lambda r: r["date"], reverse=True)
        if len(mine) > STOCK_READ_DILUTION_KEEP_PER_KIND:
            more.append(kind)
        filings += mine[:STOCK_READ_DILUTION_KEEP_PER_KIND]
    name = payload.get("name")
    return {"name": name.strip() if isinstance(name, str) and name.strip() else None, "filings": filings,
            "more": more, "unread_to": max(unread) if unread else None}


# -- the row ---------------------------------------------------------------------------------------------
def _span(days: int) -> str:
    if days >= 365 and days % 365 == 0:
        return f"{days // 365} year{'s' if days != 365 else ''}"
    return f"{days} days"


def _when(ts: float) -> str:
    dt = datetime.fromtimestamp(float(ts), ET)
    return f"{dt:%b} {dt.day} {dt:%H:%M} ET"


def _row(value: str, state: str, detail: str, as_of: float | None = None) -> dict[str, Any]:
    return {"id": ROW_ID, "label": ROW_LABEL, "value": value, "detail": detail, "state": state,
            "source": STOCK_READ_DILUTION_SOURCE, "as_of": as_of}


def _value(kind: str, flag: Mapping[str, Any]) -> str:
    month = str(flag["date"])[:7]
    if kind == "shelf":
        return f"{flag['form']} shelf {month}"
    if kind == "placement":
        return f"{flag['form']} {STOCK_READ_DILUTION_PLACEMENT_ITEM} {month}"
    return f"{flag['form']} {month}"


def _sentence(kind: str, flag: Mapping[str, Any], capped: bool) -> str:
    form = f"{flag['form']} Item {STOCK_READ_DILUTION_PLACEMENT_ITEM}" if kind == "placement" else flag["form"]
    count = int(flag["count"])
    many = f" ({count}{'+' if capped else ''} in the last {_span(DAYS[kind])})" if count > 1 else ""
    return f"{FILED[kind]}: {form} filed {flag['date']}{many}."


def _refresh_note(view: Mapping[str, Any]) -> str:
    """What is happening to a read that is no longer fresh."""
    if view.get("error"):
        return f"EDGAR could not be read again: {view['error']}."
    return "A new read of EDGAR is under way."


def row(view: Mapping[str, Any] | None, now: float) -> dict[str, Any]:
    """The read's row from the reader's answer for the symbol. ``warn``: a kind is on file. ``ok``: the
    registrant is known, the list was read back far enough and none is. ``unknown``: anything else, with
    the reason -- never read as clean."""
    if not view:
        return _row("Not known", "unknown", "The EDGAR reader could not be asked.")
    status, sym = view.get("status"), view.get("symbol") or "it"
    fetched = view.get("fetched_at")
    if status == "off":
        return _row("Not read", "unknown", f"The EDGAR reader is off ({STOCK_READ_DILUTION_ENV}=0).")
    if status == "reading":
        return _row("Not read yet", "unknown", f"Reading EDGAR… the first read of SEC's filings for {sym} is under way.")
    if status == "error":
        again = f" Nova asks again after {_when(view['retry_at'])}." if view.get("retry_at") else ""
        return _row("Not known", "unknown", f"EDGAR could not be read: {view.get('error') or 'no reason given'}.{again}")
    if status == "no_cik":
        note = f" {_refresh_note(view)}" if view.get("stale") else ""
        listed_at = view.get("listed_at") or fetched
        listed = f" (list read {_when(listed_at)})" if listed_at else ""
        return _row("Not known", "unknown", f"SEC's ticker list has no registrant for {sym}{listed}, so its filings "
                                            f"cannot be looked up.{note}")
    if status != "read" or fetched is None:
        return _row("Not known", "unknown", "The EDGAR reader gave no answer.")

    found = flags(view.get("filings") or [], view.get("unread_to"), today_et(now))
    on = [kind for kind in KINDS if found[kind]["state"] == "on_file"]
    unknown = [kind for kind in KINDS if found[kind]["state"] == "unknown"]
    who = f" for {view['name']}" if view.get("name") else ""
    read = f"EDGAR read {_when(fetched)}{who} (CIK {view.get('cik')})."
    stale = f" {_refresh_note(view)}" if view.get("stale") else ""
    unread = ""
    if unknown:
        unread = (f" Not known: {', '.join(ABSENT[kind] for kind in unknown)} -- EDGAR lists filings up to "
                  f"{view.get('unread_to')} that Nova did not read.")
    if on:
        capped = set(view.get("more") or [])
        said = " ".join(_sentence(kind, found[kind], kind in capped) for kind in on)
        return _row(", ".join(_value(kind, found[kind]) for kind in on), "warn", f"{said}{unread} {read}{stale}",
                    fetched)
    if view.get("stale"):
        return _row("Not known", "unknown", f"The last read found none on file. {read}{stale}", fetched)
    if unknown:
        return _row("Not known", "unknown", f"None found in what was read.{unread} {read}", fetched)
    checked = ", ".join(f"no {ABSENT[kind]} in {_span(DAYS[kind])}" for kind in KINDS)
    return _row("None on file", "ok", f"{checked[0].upper()}{checked[1:]}. {read}", fetched)
