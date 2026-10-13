"""NYSE breadth (ADR 053): IBKR's four NYSE market indicators, sampled once a minute in the regular session.

AD-NYSE carries advancing issues in its bid and declining in its ask (unchanged in the bid size); VOL-NYSE up
volume in its bid, down volume in its ask; TICK-NYSE and TRIN-NYSE their value in ``last`` (IBKR TWS API, Market
Indicators). The day's samples are kept in ``breadth-<date>.json`` so a restart keeps the up-minus-down line, and
the last one in ``breadth-last.json`` so the next premarket can show it as the prior session's close.
"""
from __future__ import annotations

import threading
from datetime import date, timedelta
from typing import Any

from constants_market_board import MARKET_BREADTH_KEEP_DAYS
from constants_scanner import SESSION_RTH_OPEN_MIN_ET
from market_board import disk
from market_board.clock import at, close_minute

LAST_FILE = "breadth-last.json"
_lock = threading.Lock()
_day: dict[str, Any] = {"date": None, "line_since": None, "samples": []}


def sample_from(quotes: dict[str, dict]) -> dict[str, Any] | None:
    """One sample from the four indicators' snapshots, or ``None`` when AD-NYSE gave no counts."""
    ad, vol, tick, trin = (quotes.get(k) or {} for k in ("ad", "vol", "tick", "trin"))
    if ad.get("bid") is None or ad.get("ask") is None:
        return None
    return {
        "advancing": ad.get("bid"), "declining": ad.get("ask"), "unchanged": ad.get("bid_size"),
        "up_volume": vol.get("bid"), "down_volume": vol.get("ask"),
        "tick": tick.get("last"), "trin": trin.get("last"),
        "data_type": ad.get("data_type"), "at": ad.get("at"),
    }


def _file(day: str) -> str:
    return f"breadth-{day}.json"


def _ensure_day(day: str) -> None:
    if _day["date"] == day:
        return
    data = disk.read(_file(day)) or {}
    _day.update(date=day, line_since=data.get("line_since"), samples=list(data.get("samples") or []))


def record(sample: dict[str, Any], day: date, now: float) -> None:
    """Keep ``sample`` as this minute's point of ``day``'s line, and as the last session's close."""
    iso = day.isoformat()
    t = float(sample.get("at") or now)
    with _lock:
        _ensure_day(iso)
        samples = _day["samples"]
        minute = int(t // 60)
        if samples and int(samples[-1][0] // 60) == minute:
            samples[-1] = [t, sample["advancing"], sample["declining"], sample.get("tick")]
        else:
            samples.append([t, sample["advancing"], sample["declining"], sample.get("tick")])
        if _day["line_since"] is None:
            _day["line_since"] = max(t, at(day, SESSION_RTH_OPEN_MIN_ET))
        disk.write(_file(iso), {"date": iso, "line_since": _day["line_since"], "samples": samples})
        disk.write(LAST_FILE, {"date": iso, **{k: sample.get(k) for k in (
            "advancing", "declining", "unchanged", "up_volume", "down_volume", "tick", "trin", "at")}})
    _prune(day)


def _prune(day: date) -> None:
    keep = {(day - timedelta(days=i)).isoformat() for i in range(MARKET_BREADTH_KEEP_DAYS)}
    for name in disk.names("breadth-20"):
        if name.removeprefix("breadth-").removesuffix(".json") not in keep:
            disk.remove(name)


def compose(now: float, day: date, phase: str, latest: dict[str, Any] | None, error: str | None) -> dict[str, Any]:
    """The wire's ``breadth`` block."""
    iso = day.isoformat()
    with _lock:
        _ensure_day(iso)
        samples = list(_day["samples"])
        line_since = _day["line_since"]
    last_file = disk.read(LAST_FILE)
    prior = None
    if last_file and last_file.get("date") and last_file["date"] < iso:
        prior = {k: last_file.get(k) for k in ("date", "advancing", "declining", "up_volume", "down_volume",
                                                "tick", "trin")}
    opened = now >= at(day, SESSION_RTH_OPEN_MIN_ET)
    base = {"advancing": None, "declining": None, "unchanged": None, "up_volume": None, "down_volume": None,
            "tick": None, "trin": None, "at": None, "data_type": None}
    line = [[s[0], s[1] - s[2]] for s in samples if s[1] is not None and s[2] is not None]
    if not opened and phase in ("premarket", "closed") and not samples:
        return {"state": "waiting", "why": "NYSE publishes breadth from 09:30 ET", **base, "ad_line": [],
                "line_since": None, "prior": prior}
    shown = latest if latest is not None and now - float(latest.get("at") or 0) < 180 else None
    if shown is None and samples:
        s = samples[-1]
        shown = {"advancing": s[1], "declining": s[2], "tick": s[3], "at": s[0]}
    if shown is None:
        why = error or ("waiting for the first sample" if now < at(day, close_minute(day)) else "no sample today")
        return {"state": "unavailable", "why": why, **base, "ad_line": line, "line_since": line_since,
                "prior": prior}
    return {"state": "ok", "why": None, **{**base, **{k: shown.get(k) for k in base}}, "ad_line": line,
            "line_since": line_since, "prior": prior}


def reset_for_tests() -> None:
    with _lock:
        _day.update(date=None, line_since=None, samples=[])
