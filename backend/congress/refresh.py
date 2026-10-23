"""The Congress reader (ADR 066, decision 7): one daemon thread, one request at a time, after the operator's agreement.

Each turn does the first thing due: the members (daily, and who left while a filer is unmatched), the House indexes
and the Senate search (hourly), then one unread report (newest first) and one portrait in turn -- so faces arrive
while a long first read goes on, not after it. Every request goes through one ``Net`` (a second apart); from 09:30 to
16:00 ET on a weekday it also waits ``CONGRESS_SESSION_GAP_SEC`` between downloads (reports and portraits). A failure
is the source's stated status and a retry; what was read stays. ``NOVA_CONGRESS=0`` runs nothing.
``run_once`` is one turn, for tests.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from congress import consent, house, photos, roster, senate
from congress.constants_congress import (
    CONGRESS_ENV,
    CONGRESS_IDLE_WAIT_SEC,
    CONGRESS_POLL_SEC,
    CONGRESS_RETRY_SEC,
    CONGRESS_SENATE_OVERLAP_DAYS,
    CONGRESS_SESSION_GAP_SEC,
    CONGRESS_YEARS_KEPT,
)
from congress.net import Net
from congress.state import book, source, sources
from congress.store import Store

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")

_thread: threading.Thread | None = None
_lock = threading.Lock()
_wake = threading.Event()
_stop = threading.Event()
_ctx: dict = {}


def enabled() -> bool:
    return (os.environ.get(CONGRESS_ENV) or "1").strip() != "0"


def today(now: float) -> date:
    return datetime.fromtimestamp(now, ET).date()


def in_session(now: float) -> bool:
    t = datetime.fromtimestamp(now, ET)
    return t.weekday() < 5 and (9 * 60 + 30) <= t.hour * 60 + t.minute < 16 * 60


def _store() -> Store:
    if "store" not in _ctx:
        _ctx["store"] = Store()
    return _ctx["store"]


def _net() -> Net:
    return _ctx.setdefault("net", Net())


def _set(key: str, state: str, now: float | None = None, error: str | None = None, **more) -> None:
    s = source(key)
    s.state, s.error = state, error
    if now is not None and state in ("ok", "reading"):
        s.read_at = now
    for k, v in more.items():
        setattr(s, k, v)


def _load() -> None:
    """The kept reports into memory, once per process (after the agreement: before it, nothing is shown)."""
    if not book().loaded:
        st = _store()
        book().replace(st.reports(), st.rows())


def _put(report: dict, rows: list[dict] | None) -> None:
    _store().put(report, rows)
    book().put(report, rows)


def _unmatched(reports: dict[str, dict]) -> list[dict]:
    return [r for r in reports.values() if not r.get("bioguide")]


def _rematch() -> None:
    from congress import matching

    members = roster.members()
    for r in _unmatched(book().snapshot()[1]):
        if r["chamber"] == "house":
            found = matching.house(members, r.get("filer_first") or "", r.get("filer_last") or "",
                                   f"{r.get('filer_state') or ''}{r.get('filer_district') or ''}")
        else:
            found = matching.senate(members, r.get("filer_first") or "", r.get("filer_last") or "")
        if found:
            _store().set_fields(r["id"], bioguide=found)
            book().set_fields(r["id"], bioguide=found)


def _roster_step(now: float) -> bool:
    unmatched = bool(_unmatched(book().snapshot()[1]))
    want_past = unmatched and roster.historical_due(now)
    if not roster.due(now) and not want_past:
        return False
    _set("roster", "reading")
    try:
        roster.refresh(_net(), now, historical=want_past)
    except Exception as exc:  # noqa: BLE001 -- stated on the page; the kept roster stays
        logger.warning("congress: the members could not be read: %s", exc)
        _set("roster", "failing", error=f"{exc}"[:200], next_at=now + CONGRESS_RETRY_SEC)
        _ctx["roster_retry"] = now + CONGRESS_RETRY_SEC
        return True
    _rematch()
    _set("roster", "ok", now, next_at=None)
    return True


def _house_step(now: float) -> bool:
    if now < _ctx.get("house_next", 0.0):
        return False
    known = set(book().snapshot()[1])
    members = roster.members()
    year = today(now).year
    try:
        for y in range(year - CONGRESS_YEARS_KEPT + 1, year + 1):
            for rec in house.sync_index(_net(), _store(), y, members, known):
                _put(rec, [])
                known.add(rec["id"])
    except Exception as exc:  # noqa: BLE001 -- stated on the page; retried
        logger.warning("congress: the House index could not be read: %s", exc)
        _ctx["house_next"] = now + CONGRESS_RETRY_SEC
        _set("house", "failing", error=f"{exc}"[:200], next_at=_ctx["house_next"])
        return True
    _ctx["house_next"] = now + CONGRESS_POLL_SEC
    _set("house", "ok", now, next_at=_ctx["house_next"])
    return True


def _senate_session():
    if "senate_session" not in _ctx:
        _ctx["senate_session"] = senate.open_session(_net())
    return _ctx["senate_session"]


def _senate_step(now: float) -> bool:
    if now < _ctx.get("senate_next", 0.0):
        return False
    st = _store()
    end = today(now)
    kept_through = st.meta("senate:read_through")
    start = (date.fromisoformat(kept_through) - timedelta(days=CONGRESS_SENATE_OVERLAP_DAYS) if kept_through
             else date(end.year - CONGRESS_YEARS_KEPT + 1, 1, 1))
    members = roster.members()
    try:
        found = senate.search(_net(), _senate_session(), start, end)
    except Exception as exc:  # noqa: BLE001 -- stated on the page; a new session next time
        logger.warning("congress: the Senate search could not be read: %s", exc)
        _ctx.pop("senate_session", None)
        _ctx["senate_next"] = now + CONGRESS_RETRY_SEC
        _set("senate", "failing", error=f"{exc}"[:200], next_at=_ctx["senate_next"])
        return True
    reports = book().snapshot()[1]
    for r in found:
        if r.id in reports:
            continue
        rec = senate.record(r, members)
        _put(rec, [])
        reports[rec["id"]] = rec
    # an amendment may be found before or after the report it corrects: settle them over everything kept
    for rid, by in senate.reconcile(reports).items():
        _store().set_fields(rid, amended_by=by)
        book().set_fields(rid, amended_by=by)
    st.set_meta("senate:read_through", end.isoformat())
    _ctx["senate_next"] = now + CONGRESS_POLL_SEC
    _set("senate", "ok", now, next_at=_ctx["senate_next"])
    return True


def _pending() -> list[dict]:
    reports = book().snapshot()[1].values()
    todo = [r for r in reports if house.pending(r) or senate.pending(r)]
    return sorted(todo, key=lambda r: (r["filed"], r["id"]), reverse=True)


def _report_step(now: float) -> bool:
    todo = _pending()
    for key in ("house", "senate"):
        left = sum(1 for r in todo if r["chamber"] == key)
        s = source(key)
        if s.state in ("ok", "reading"):
            s.state = "reading" if left else "ok"
        s.todo = left
    if not todo:
        return False
    retry = _ctx.setdefault("retry_at", {})
    due = [r for r in todo if retry.get(r["id"], float("-inf")) <= now]
    if not due:                                     # every unread report failed lately: each waits its own retry
        _ctx["soon"] = min(retry[r["id"]] for r in todo) - now
        return False
    if _session_wait(now):
        return False
    report = due[0]
    try:
        if report["chamber"] == "house":
            updated, rows = house.read(_net(), report, now)
        else:
            updated, rows = senate.read(_net(), _senate_session(), report, now)
    except senate.SenateRefused as exc:
        _ctx.pop("senate_session", None)
        retry[report["id"]] = now + CONGRESS_RETRY_SEC
        _set("senate", "failing", error=str(exc)[:200])
        return True
    except Exception as exc:  # noqa: BLE001 -- one report's failure is stated on it, never stops the others
        logger.warning("congress: report %s could not be read: %s", report["id"], exc)
        updated, rows = {**report, "error": f"{exc}"[:200]}, None
    _ctx["last_download_at"] = now
    if rows is None:                                # not read (the site failed): it waits, the others go on
        retry[report["id"]] = now + CONGRESS_RETRY_SEC
    else:
        retry.pop(report["id"], None)
    _put(updated, rows)
    source(report["chamber"]).done += 1
    return True


def _session_wait(now: float) -> bool:
    """True while the session's gap since the last download (a report or a portrait) is not over."""
    wait = _ctx.get("last_download_at", float("-inf")) + CONGRESS_SESSION_GAP_SEC - now
    if in_session(now) and wait > 0:
        _ctx["soon"] = wait                         # the loop wakes when the gap is over
        return True
    return False


def _photo_step(now: float) -> bool:
    if now < _ctx.get("photo_retry", 0.0):
        return False
    _, reports, _ = book().snapshot()
    filers = [r["bioguide"] for r in sorted(reports.values(), key=lambda r: r["filed"], reverse=True) if r.get("bioguide")]
    seated = [m["bioguide"] for m in roster.members() if m.get("current")]
    wanted = photos.wanted(filers + seated, now)
    if not wanted:
        _set("photos", "ok", now, todo=0)
        return False
    if _session_wait(now):
        return False
    _set("photos", "reading", todo=len(wanted))
    _ctx["last_download_at"] = now
    try:
        photos.fetch(_net(), wanted[0], now)
    except Exception as exc:  # noqa: BLE001 -- the site failed, not the member: every portrait waits; initials meanwhile
        logger.warning("congress: the portrait of %s could not be read: %s", wanted[0], exc)
        _set("photos", "failing", error=f"{exc}"[:200], todo=len(wanted), next_at=now + CONGRESS_RETRY_SEC)
        _ctx["photo_retry"] = now + CONGRESS_RETRY_SEC
        return True
    source("photos").done += 1
    return True


def _report_or_photo(now: float) -> bool:
    """An unread report and a portrait take turns; either goes alone when the other has nothing due."""
    turn = (_photo_step, _report_step) if _ctx.get("photo_turn") else (_report_step, _photo_step)
    _ctx["photo_turn"] = not _ctx.get("photo_turn")
    return turn[0](now) or turn[1](now)


def run_once(now: float | None = None) -> bool:
    """Do the first thing due; False when nothing was."""
    now = time.time() if now is None else now
    if not enabled():
        for s in sources():
            s.state = "off"
        return False
    if not consent.given():
        for s in sources():
            s.state = "needs_consent"
        return False
    for s in sources():
        if s.state in ("off", "needs_consent"):
            s.state = "waiting"
    _load()
    if now >= _ctx.get("roster_retry", 0.0) and _roster_step(now):
        return True
    return _house_step(now) or _senate_step(now) or _report_or_photo(now)


def start() -> None:
    """Start the reader once (the process start, or the agreement given)."""
    global _thread
    if not enabled():
        return
    with _lock:
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_loop, daemon=True, name="congress")
            _thread.start()


def wake() -> None:
    start()
    _wake.set()


def _loop() -> None:
    while not _stop.is_set():
        try:
            if run_once():
                continue
            _wake.wait(min(CONGRESS_IDLE_WAIT_SEC, _ctx.pop("soon", CONGRESS_IDLE_WAIT_SEC)))
            _wake.clear()
        except Exception:  # noqa: BLE001 -- the reader must outlive any one bad turn
            logger.exception("congress reader")
            _stop.wait(5.0)


def stop_for_tests(timeout: float = 5.0) -> bool:
    global _thread
    _stop.set()
    _wake.set()
    with _lock:
        thread, _thread = _thread, None
    if thread is not None:
        thread.join(timeout)
    _stop.clear()
    return thread is None or not thread.is_alive()


def reset_for_tests(net=None) -> None:
    store = _ctx.pop("store", None)
    if store is not None:
        store.close()
    _ctx.clear()
    if net is not None:
        _ctx["net"] = net
