"""Pure collectors: gateway, market-data and recorder rows (ADR 021).

Inputs are plain dicts the gather shell reads from ``ibkr.*`` and
``capture.*``; nothing here touches an IB object.
"""
from __future__ import annotations

import time
from typing import Any

from constants_diagnostics import (
    DIAG_ACTION_LAUNCH_GATEWAY,
    DIAG_ACTION_RECONNECT_IBKR,
    DIAG_GROUP_GATEWAY,
    DIAG_GROUP_MARKET_DATA,
    DIAG_GROUP_RECORDER,
    DIAG_STATE_FAIL,
    DIAG_STATE_OFF,
    DIAG_STATE_OK,
    DIAG_STATE_UNKNOWN,
    DIAG_STATE_WARN,
)
from diagnostics.rows import row

_HUMAN_STEP_COPY: dict[str, str] = {
    "second_factor_pending": "IBKR Mobile 2FA prompt is open on the Gateway desktop -- approve it there.",
    "client_id_in_use": "Another Nova API holds clientId 17 -- stop the extra process (one API on :8000).",
    "account_kind_mismatch": "The Gateway is logged into the other account kind (paper vs live) -- log in with the right one.",
    "attach_cap": "Nova attached 5 times in 10 minutes without reaching READY -- the Gateway is still authenticating or waiting for a login; finish it on the desktop.",
}


def _fmt_ts(ts: float | None) -> str:
    if not ts:
        return "never"
    return time.strftime("%H:%M:%S", time.localtime(float(ts)))


# ── Gateway ───────────────────────────────────────────────────────────────────

def gateway_rows(
    *,
    enabled: bool,
    session: dict[str, Any],
    ports: dict[str, Any],
    ibc: dict[str, Any],
    last_error: dict[str, Any] | None,
    attach: dict[str, Any],
    heal: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    live_port, paper_port = ports.get("live_port"), ports.get("paper_port")
    live_up, paper_up = ports.get("live_reachable"), ports.get("paper_reachable")
    if live_up is None and paper_up is None:
        p_state, p_detail = DIAG_STATE_UNKNOWN, "Unknown: port probes were skipped"
        p_cause, p_fix = "The probe did not run (IBKR disabled).", "Enable IBKR and Refresh."
    elif live_up:
        p_state, p_detail = DIAG_STATE_OK, f"live Gateway API port {live_port} answers TCP"
        p_cause, p_fix = "IB Gateway is running with its API listening.", "Nothing to do."
    elif paper_up:
        p_state, p_detail = DIAG_STATE_WARN, f"only the legacy paper Gateway port {paper_port} answers; live {live_port} is dark"
        p_cause = "The paper Gateway is up but Nova targets live (ADR 020: the live Gateway is the one data door)."
        p_fix = "Log into the live Gateway (Launch Gateway), or switch the door by hand if you mean the legacy paper Gateway."
    else:
        p_state, p_detail = DIAG_STATE_FAIL, f"neither Gateway port answers ({live_port} / {paper_port})"
        p_cause, p_fix = "IB Gateway is not running, or its API port is off.", "Launch Gateway and complete the IBC login / 2FA."
    rows.append(row(
        id="gateway_port",
        group=DIAG_GROUP_GATEWAY,
        title="Gateway API port",
        state=p_state,
        detail=p_detail,
        cause=p_cause,
        fix=p_fix,
        action=DIAG_ACTION_LAUNCH_GATEWAY if p_state == DIAG_STATE_FAIL else None,
        evidence=dict(ports),
    ))

    pending, stale = bool(ibc.get("second_factor_pending")), bool(ibc.get("second_factor_stale"))
    if stale:
        i_state, i_detail = DIAG_STATE_FAIL, "Second Factor prompt on screen has expired"
        i_cause, i_fix = "IBC discards a login whose 2FA took longer than its own timeout.", "Start a fresh login (Launch Gateway) and approve the new prompt promptly."
    elif pending:
        i_state = DIAG_STATE_WARN
        i_detail = f"Second Factor prompt open for {round(float(ibc.get('second_factor_age_sec') or 0))}s"
        i_cause, i_fix = "IBKR Mobile 2FA is waiting for you -- Nova never approves it.", "Approve the prompt on your phone."
    elif not ibc.get("launcher_present"):
        i_state, i_detail = DIAG_STATE_OFF, "IBC launcher not installed (Launch Gateway cannot prefill the login)"
        i_cause, i_fix = "%USERPROFILE%\\.nova\\ibc\\start_gateway.ps1 is missing.", "See docs/ibc-gateway-setup.md."
    else:
        i_state, i_detail = DIAG_STATE_OK, "IBC launcher present; no 2FA prompt pending"
        i_cause, i_fix = "Login automation is available.", "Nothing to do."
    rows.append(row(
        id="gateway_ibc_login",
        group=DIAG_GROUP_GATEWAY,
        title="IBC login / 2FA",
        state=i_state,
        detail=i_detail,
        cause=i_cause,
        fix=i_fix,
        action=DIAG_ACTION_LAUNCH_GATEWAY if stale else None,
        evidence=dict(ibc),
    ))

    state_name, reason = str(session.get("state")), str(session.get("reason"))
    usable, transport = bool(session.get("usable")), bool(session.get("transport_up"))
    port_open = bool(live_up or paper_up)
    if not enabled:
        s_state, s_detail = DIAG_STATE_OFF, f"IBKR disabled in this process (state {state_name}, reason {reason})"
        s_cause, s_fix = "IBKR_ENABLED is not true for this API process -- the dialer never dials.", "See the integrations rows: fix .env, then Reload backend."
        s_action = None
    elif usable:
        s_state, s_detail = DIAG_STATE_OK, f"session READY (generation {session.get('generation')}, {session.get('mode')})"
        s_cause, s_fix, s_action = "Account kind accepted and caches warm.", "Nothing to do.", None
    elif transport:
        s_state, s_detail = DIAG_STATE_WARN, f"socket up, session not READY (state {state_name}, reason {reason})"
        s_cause = "Nova connected to the Gateway but did not finish validating the account / warming caches (Error 1100, paper-pin reject, or a stuck warm-up)."
        s_fix = "Reconnect Nova to Gateway; the watchdog also resets a stuck session on its own."
        s_action = DIAG_ACTION_RECONNECT_IBKR
    elif port_open:
        s_state, s_detail = DIAG_STATE_FAIL, f"Gateway port open but Nova is not attached (state {state_name}, reason {reason})"
        s_cause = "The Gateway is still authenticating, another API holds the clientId, or Nova has not dialed yet."
        s_fix = "Watch the attach retry row; Reconnect Nova to Gateway if it stays here."
        s_action = DIAG_ACTION_RECONNECT_IBKR
    else:
        s_state, s_detail = DIAG_STATE_FAIL, f"disconnected (state {state_name}, reason {reason})"
        s_cause, s_fix, s_action = "No Gateway to attach to.", "Launch Gateway and log in.", DIAG_ACTION_LAUNCH_GATEWAY
    rows.append(row(
        id="gateway_session",
        group=DIAG_GROUP_GATEWAY,
        title="Nova session",
        state=s_state,
        detail=s_detail,
        cause=s_cause,
        fix=s_fix,
        since=session.get("unusable_since"),
        action=s_action,
        evidence={**session, "connect_last_result": heal.get("connect_last_result"), "connect_last_reason": heal.get("connect_last_reason"), "gateway_self_heal": heal.get("gateway_self_heal")},
    ))

    if last_error:
        e_state = DIAG_STATE_WARN
        e_detail = f"last IB error {last_error.get('code')} at {_fmt_ts(last_error.get('ts'))}: {last_error.get('message') or ''}".strip()
        e_cause, e_fix = "The most recent errorEvent from the Gateway, any code.", "Look the code up in the IBKR API docs if it is not one Nova names."
    else:
        e_state, e_detail = DIAG_STATE_OK, "no IB error on this connection"
        e_cause, e_fix = "No errorEvent since the last session reset.", "Nothing to do."
    rows.append(row(
        id="gateway_last_error",
        group=DIAG_GROUP_GATEWAY,
        title="Last IB error",
        state=e_state,
        detail=e_detail,
        cause=e_cause,
        fix=e_fix,
        since=(last_error or {}).get("ts"),
        evidence=dict(last_error or {}),
    ))

    human = attach.get("human_step")
    attempts = int(attach.get("attempts_in_window") or 0)
    if usable:
        a_state, a_detail = DIAG_STATE_OK, "not retrying -- session READY"
        a_cause, a_fix = "The attach ledger clears on READY.", "Nothing to do."
    elif human:
        a_state, a_detail = DIAG_STATE_WARN, f"waiting for you: {human} (polling every {attach.get('human_step_poll_sec')}s)"
        a_cause = _HUMAN_STEP_COPY.get(str(human), "A step Nova cannot take on its own.")
        a_fix = "Do the step on the Gateway desktop; Nova attaches on the next poll."
    elif attempts:
        a_state, a_detail = DIAG_STATE_WARN, f"{attempts} attach attempt(s) in the last 10 min; next in {attach.get('next_delay_sec')}s"
        a_cause, a_fix = "Port open, session not READY -- Nova retries on its own (1, 2, 5, 10, 30 s).", "Nothing to do yet; it caps at 5 per 10 min and then says so."
    else:
        a_state, a_detail = DIAG_STATE_OFF, "no attach attempts recorded"
        a_cause, a_fix = "Nothing to retry (disabled, dark ports, or already READY).", "Nothing to do."
    rows.append(row(
        id="gateway_attach_retry",
        group=DIAG_GROUP_GATEWAY,
        title="Attach retry",
        state=a_state,
        detail=a_detail,
        cause=a_cause,
        fix=a_fix,
        since=(attach.get("last_attempt") or {}).get("ts"),
        evidence={k: v for k, v in attach.items() if k != "recent"} | {"recent": list(attach.get("recent") or [])[-5:]},
    ))
    return rows


# ── Market data ───────────────────────────────────────────────────────────────

def market_data_rows(
    *,
    usable: bool,
    delayed: bool,
    live_md_blocked: bool,
    data_farm: dict[str, Any],
    max_tickers: bool,
    budget: dict[str, Any],
    depth_symbols: list[str],
    tape_symbols: list[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not usable:
        m_state, m_detail = DIAG_STATE_OFF, "no session -- entitlement unknown until READY"
        m_cause, m_fix = "Market-data errors only arrive on a connected session.", "Attach first."
    elif live_md_blocked:
        m_state, m_detail = DIAG_STATE_FAIL, "live API market data not entitled (Error 10089) -- delayed fallback"
        m_cause = "This login has no live API data subscription (or paper is not sharing it)."
        m_fix = "Share real-time market data with this login in IBKR Account Management, then reconnect."
    elif delayed:
        m_state, m_detail = DIAG_STATE_WARN, "delayed market data (Error 10167)"
        m_cause, m_fix = "The Gateway is serving delayed quotes for at least one request.", "Check the data subscription for that symbol's exchange."
    else:
        m_state, m_detail = DIAG_STATE_OK, "live market data (no entitlement error this session)"
        m_cause, m_fix = "No 10089 / 10167 since the last session reset.", "Nothing to do."
    rows.append(row(
        id="market_data_entitlement",
        group=DIAG_GROUP_MARKET_DATA,
        title="Entitlement",
        state=m_state,
        detail=m_detail,
        cause=m_cause,
        fix=m_fix,
        evidence={"delayed": delayed, "live_md_blocked": live_md_blocked, "data_farm": data_farm, "max_tickers": max_tickers},
    ))
    lines = int(budget.get("reqMktData_lines") or budget.get("lines") or 0)
    limit = budget.get("limit") or budget.get("budget")
    rows.append(row(
        id="market_data_lines",
        group=DIAG_GROUP_MARKET_DATA,
        title="Lines held",
        state=DIAG_STATE_WARN if max_tickers else (DIAG_STATE_OK if usable else DIAG_STATE_OFF),
        detail=(
            f"L1 {lines}{f'/{limit}' if limit else ''} · depth {len(depth_symbols)} · tape {len(tape_symbols)}"
            + (" · Error 101 max tickers hit" if max_tickers else "")
        ),
        cause="What this process is asking the Gateway to stream right now." if not max_tickers else "The Gateway refused a new line: the account's ticker budget is used up.",
        fix="Nothing to do." if not max_tickers else "Close Trader tabs / scanner lists you are not watching.",
        evidence={"budget": budget, "depth_symbols": depth_symbols, "tape_symbols": tape_symbols, "max_tickers": max_tickers},
    ))
    return rows


# ── Recorder ──────────────────────────────────────────────────────────────────

def recorder_rows(
    *,
    recording: list[str],
    sessions: dict[str, Any],
    resume: list[dict[str, Any]],
    stopped: list[dict[str, Any]],
    error: str | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not recording:
        r_state, r_detail = DIAG_STATE_OFF, "not recording"
        r_cause, r_fix = "No Session Record is running.", "Nothing to do."
    elif error or any(not (sessions.get(s) or {}).get("healthy", True) for s in recording):
        r_state, r_detail = DIAG_STATE_WARN, f"recording {', '.join(recording)} with a problem: {error or 'a symbol is unhealthy'}"
        r_cause, r_fix = "The recorder is up but a line or the writer reported an error.", "Watch the resume row; keepalive re-acquires lines on its own."
    else:
        r_state, r_detail = DIAG_STATE_OK, f"recording {', '.join(recording)}"
        r_cause, r_fix = "Tape + depth lines held by Record.", "Nothing to do."
    rows.append(row(
        id="recorder_state",
        group=DIAG_GROUP_RECORDER,
        title="Session Record",
        state=r_state,
        detail=r_detail,
        cause=r_cause,
        fix=r_fix,
        evidence={"recording": recording, "sessions": sessions, "error": error},
    ))
    pending = [r for r in resume if r.get("pending")]
    gave_up = [r for r in resume if r.get("gave_up")]
    if gave_up:
        k_state = DIAG_STATE_FAIL
        k_detail = "keepalive gave up on " + ", ".join(str(r.get("symbol")) for r in gave_up)
        k_cause = "Resume failed CAPTURE_RESUME_MAX_ATTEMPTS times (" + "; ".join(str(r.get("gave_up_reason")) for r in gave_up) + ")."
        k_fix = "Start the recording again by hand once the cause is fixed."
    elif pending:
        k_state = DIAG_STATE_WARN
        k_detail = "resuming " + ", ".join(f"{r.get('symbol')} (attempt {r.get('attempt')}/{r.get('max_attempts')})" for r in pending)
        k_cause, k_fix = "An unplanned stop; keepalive is bringing it back with backoff.", "Nothing to do."
    elif stopped:
        last = stopped[-1]
        k_state = DIAG_STATE_WARN
        k_detail = f"last unplanned stop: {last.get('symbol')} at {_fmt_ts(last.get('at'))} ({last.get('reason')})"
        k_cause = str(last.get("error") or "The recorder stopped without an operator Stop.")
        k_fix = "Resumed already" if last.get("resumed") else "Record again by hand if you still want this session."
    else:
        k_state, k_detail = DIAG_STATE_OK, "no unplanned stops"
        k_cause, k_fix = "Every stop so far was an operator Stop.", "Nothing to do."
    rows.append(row(
        id="recorder_keepalive",
        group=DIAG_GROUP_RECORDER,
        title="Keepalive",
        state=k_state,
        detail=k_detail,
        cause=k_cause,
        fix=k_fix,
        since=(stopped[-1].get("at") if stopped else None),
        evidence={"resume": resume, "stopped": stopped},
    ))
    return rows
