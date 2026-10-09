"""Diagnostics row for IBKR's data farms and line notices (#722).

``ibkr.farm_notices`` keeps every farm broken / OK / inactive notice, depth halted (316) and
competing live session (10197) with its farm and time. This row says which farm is broken now and
what IBKR said in the last half hour, so a Time & Sales that went silent can be held up against a
farm event. It reports only: Nova does not reconnect or restart anything for a farm notice.
"""
from __future__ import annotations

import time
from typing import Any

from constants_diagnostics import (
    DIAG_GROUP_MARKET_DATA,
    DIAG_STATE_OFF,
    DIAG_STATE_OK,
    DIAG_STATE_WARN,
)
from constants_ibkr import IBKR_NOTICES_DIAG_WINDOW_SEC
from diagnostics.rows import row

_RECENT_EVIDENCE = 20
_FIX = ("Nothing to press: IBKR restores a farm itself and says OK (2104 / 2106 / 2158), and Nova does "
        "not reconnect for a notice, which would also drop the order channel. If a Time & Sales reads "
        "LINE DOWN at the same time, the two are one event.")


def _clock(ts: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(float(ts)))


def _said(n: dict[str, Any]) -> str:
    who = n.get("farm") or n.get("symbol") or ""
    return f"{n['code']} {n['notice'].replace('_', ' ')}{f' {who}' if who else ''} at {_clock(n['ts'])}"


def farm_rows(*, view: dict[str, Any], usable: bool, now: float) -> list[dict[str, Any]]:
    """``view`` is ``ibkr.farm_notices.view()``."""
    farms = view.get("farms") or []
    recent = [n for n in view.get("recent") or [] if n.get("ts", 0) >= now - IBKR_NOTICES_DIAG_WINDOW_SEC]
    broken = [f for f in farms if f.get("state") == "broken"]
    line_trouble = [n for n in recent if n.get("notice") in ("depth_halted", "competing_session")]
    since = None
    if not usable:
        # No session can vouch for any farm now: the last notices are evidence, not a state.
        state = DIAG_STATE_OFF
        detail = ("no session -- IBKR sends farm notices on a connected session"
                  + (f"; last word before it: {_said(recent[-1])}" if recent else ""))
        cause = "Farm states are read only while the Gateway session is up."
    elif broken:
        state = DIAG_STATE_WARN
        detail = "broken: " + ", ".join(f"{f['farm']} ({f.get('farm_type') or 'farm'}) since {_clock(f['since'])}"
                                        for f in broken)
        cause = ("IBKR said the farm connection is broken (2103 / 2105 / 2157). Lines served by it can "
                 "stop with no other error.")
        since = min(f["since"] for f in broken)
    elif line_trouble:
        state = DIAG_STATE_WARN
        detail = f"{len(line_trouble)} line notice{'s' if len(line_trouble) != 1 else ''} in the last 30 min; " \
                 f"last {_said(line_trouble[-1])}"
        cause = ("316: IBKR halted a Level 2 line and asks for it again; 10197: another live login is using "
                 "the market data.")
        since = line_trouble[-1]["ts"]
    else:
        state = DIAG_STATE_OK
        named = ", ".join(f["farm"] for f in farms)
        detail = (f"all farms OK or idle: {named}" if named else "no farm notice this session")
        if recent:
            detail += f"; {len(recent)} notice{'s' if len(recent) != 1 else ''} in the last 30 min, " \
                      f"last {_said(recent[-1])}"
        cause = "No farm is broken now."
    return [row(
        id="market_data_farms",
        group=DIAG_GROUP_MARKET_DATA,
        title="IBKR data farms",
        state=state,
        detail=detail,
        cause=cause,
        fix=_FIX if state == DIAG_STATE_WARN else "Nothing to do.",
        since=since,
        evidence={"farms": farms, "recent": (view.get("recent") or [])[-_RECENT_EVIDENCE:]},
    )]
