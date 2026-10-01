"""Diagnostics row for the IBKR feed's gaps: stretches when no market data reached Nova (#672).

On 2026-10-01 the desk's Wi-Fi re-authenticated five times at the open and the
charts and Time & Sales froze for 4-16 s each time, with nothing on the
checklist. This row says when the feed is silent now, and how often it went
silent in the last half hour and why (``ibkr.feed_pulse``, ``ibkr.wifi_drops``).
"""
from __future__ import annotations

from typing import Any

from constants_diagnostics import (
    DIAG_GROUP_MARKET_DATA,
    DIAG_STATE_FAIL,
    DIAG_STATE_OFF,
    DIAG_STATE_OK,
    DIAG_STATE_WARN,
)
from constants_feed import FEED_DIAG_WINDOW_SEC
from diagnostics.rows import row

_FIX_WIFI = ("Plug the PC into the router with a network cable; "
             "Wi-Fi drops stop the feed for seconds at a time.")
_FIX_OTHER = ("Check the network and IB Gateway; Nova and the Gateway's API connection were up. "
              "If it repeats, compare the times with the Windows WLAN log and the Gateway's own log.")


def feed_rows(*, view: dict[str, Any], now: float) -> list[dict[str, Any]]:
    """``view`` is ``ibkr.feed_pulse.view()``."""
    live = view.get("gap")
    recent = [g for g in view.get("recent") or [] if (g.get("end") or now) >= now - FEED_DIAG_WINDOW_SEC]
    wifi = [g for g in recent if g.get("cause") == "wifi"]
    if live is not None:
        state = DIAG_STATE_FAIL
        detail = f"no IBKR data on any line for {live['silent_sec']:.0f} s"
        cause = live["text"]
        fix = _FIX_WIFI if live.get("cause") == "wifi" else _FIX_OTHER
        since = live["start"]
    elif recent:
        longest = max(recent, key=lambda g: g["silent_sec"])
        state = DIAG_STATE_WARN
        detail = (f"{len(recent)} gap{'s' if len(recent) != 1 else ''} in the last 30 min, longest "
                  f"{longest['silent_sec']:.0f} s" + (f"; {len(wifi)} during Wi-Fi reconnects" if wifi else ""))
        cause = recent[0]["text"]
        fix = _FIX_WIFI if wifi else _FIX_OTHER
        since = recent[0]["start"]
    elif not view.get("connected") or not view.get("in_session"):
        state = DIAG_STATE_OFF
        detail = "not watching: " + ("IBKR is not connected" if not view.get("connected")
                                     else "outside the 04:00-20:00 ET session")
        cause = "A gap is counted only while the Gateway is connected, inside the session."
        fix = "Nothing to do."
        since = None
    else:
        state = DIAG_STATE_OK
        silent = view.get("silent_sec")
        detail = "IBKR data arriving" + (f" (last {silent:.1f} s ago)" if silent is not None else "")
        cause = "No gap in the last 30 minutes."
        fix = "Nothing to do."
        since = None
    return [row(
        id="ibkr_feed_gaps",
        group=DIAG_GROUP_MARKET_DATA,
        title="IBKR feed gaps",
        state=state,
        detail=detail,
        cause=cause,
        fix=fix,
        since=since,
        evidence={"gap": live, "recent": recent, "last_data_ts": view.get("last_data_ts"),
                  "rule": view.get("rule")},
    )]
