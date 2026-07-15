"""
Nova OS gate evaluators (Phase P2) — pure-ish helpers used by `decide()`.

Each gate returns a GateResult (and optional ticket/setup metadata). Hard gates
fail closed; soft gates (catalyst, microstructure) never alone authorize a BUY
that hard gates rejected. No orders are placed here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

from constants import (
    GAP_AND_GO_WINDOW_START_ET,
    NOVA_OS_CATALYST_MIN_CONFIDENCE,
    NOVA_OS_MIN_FIRST_MINUTE_VOLUME,
    NOVA_OS_NYSE_HOLIDAYS,
    NOVA_OS_PRIMARY_SETUP,
    NOVA_OS_WATCHLIST_MAX_RANK,
)
from market import now_et
from news.impact import evaluate_news_impact
from nova_os import codes
from strategy import risk as risk_mod
from strategy.five_pillars import evaluate_five_pillars
from strategy.setups import evaluate_setups

_ET = ZoneInfo("America/New_York")

_PILLAR_FAIL_CODE = {
    "price": "PILLAR_PRICE_FAIL",
    "change_pct": "PILLAR_CHANGE_FAIL",
    "relative_volume": "PILLAR_RVOL_FAIL",
    "catalyst": "PILLAR_CATALYST_FAIL",
    "float": "PILLAR_FLOAT_FAIL",
}

GATE_SESSION = "session"
GATE_PILLARS = "five_pillars"
GATE_SETUP = "setup"
GATE_TICKET = "ticket"
GATE_CATALYST = "catalyst"
GATE_MICROSTRUCTURE = "microstructure"


@dataclass
class GateResult:
    name: str
    passed: bool
    hard: bool
    reason_codes: list[str] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def first_minute_volume(bars: list[dict]) -> int | None:
    """Volume of the 9:30 ET 1-minute bar, or None if missing."""
    session_open = dtime(*GAP_AND_GO_WINDOW_START_ET)
    for bar in bars:
        ts_raw = bar.get("t")
        vol = bar.get("v")
        if ts_raw is None or vol is None:
            continue
        try:
            ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00")).astimezone(_ET)
        except ValueError:
            continue
        if ts.timetz().replace(tzinfo=None) == session_open:
            return int(vol)
    return None


def is_nyse_holiday(when: datetime | None = None) -> bool:
    """True when `when` (ET) falls on a known NYSE full-day holiday."""
    when = when or now_et()
    return when.date().isoformat() in NOVA_OS_NYSE_HOLIDAYS


def session_allows_trading(when: datetime | None = None) -> bool:
    """Extended-hours weekday window (04:00–20:00 ET). Weekends/holidays closed."""
    when = when or now_et()
    if when.weekday() >= 5:
        return False
    if is_nyse_holiday(when):
        return False
    minutes = when.hour * 60 + when.minute
    return (4 * 60) <= minutes < (20 * 60)


def gate_session(risk_state, requested_mode: str) -> tuple[GateResult, str, list[str]]:
    """Gate 0 — session + risk + loss-policy mode."""
    reasons: list[str] = []
    evidence: dict = {}
    can, halt_reason = risk_state.can_trade()
    evidence["can_trade"] = can
    evidence["halt_reason"] = None if can else halt_reason
    evidence["consecutive_losses"] = risk_state.consecutive_losses
    evidence["losses_today"] = risk_state.losses_today

    effective_mode, loss_reason = codes.loss_policy_mode(
        risk_state.losses_today, requested_mode
    )
    evidence["requested_mode"] = requested_mode
    evidence["effective_mode"] = effective_mode
    if loss_reason:
        reasons.append(loss_reason)
        evidence["loss_policy"] = loss_reason

    when = now_et()
    evidence["is_holiday"] = is_nyse_holiday(when)
    if evidence["is_holiday"]:
        reasons.append("SESSION_HOLIDAY")
        evidence["session_open"] = False
        return GateResult(GATE_SESSION, False, True, reasons, evidence), effective_mode, reasons

    if not session_allows_trading(when):
        reasons.append("SESSION_CLOSED")
        evidence["session_open"] = False
        return GateResult(GATE_SESSION, False, True, reasons, evidence), effective_mode, reasons

    evidence["session_open"] = True
    if not can:
        reasons.append("RISK_HALTED")
        return GateResult(GATE_SESSION, False, True, reasons, evidence), effective_mode, reasons

    return GateResult(GATE_SESSION, True, True, reasons, evidence), effective_mode, reasons


def gate_pillars(candidate: dict, technical_breakout: bool) -> GateResult:
    result = evaluate_five_pillars(candidate, technical_breakout=technical_breakout)
    if result.all_pass:
        return GateResult(
            GATE_PILLARS, True, True, ["PILLARS_PASS"], {"five_pillars": result.to_dict()}
        )
    reasons: list[str] = []
    for check in result.checks:
        if check.passed:
            continue
        if "unknown" in check.detail or check.detail.startswith("no "):
            reasons.append("PILLARS_MISSING_DATA")
        reasons.append(_PILLAR_FAIL_CODE.get(check.name, "PILLARS_MISSING_DATA"))
    seen: set[str] = set()
    ordered: list[str] = []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            ordered.append(r)
    return GateResult(
        GATE_PILLARS, False, True, ordered or ["PILLARS_MISSING_DATA"],
        {"five_pillars": result.to_dict()},
    )


def gate_setup(
    candidate: dict,
    bars: list[dict],
    watchlist_rank: int | None,
    preferred_setup: str,
) -> tuple[GateResult, str | None, dict | None]:
    setups = evaluate_setups(candidate, bars)
    primary = preferred_setup if preferred_setup in setups else NOVA_OS_PRIMARY_SETUP
    signal = setups.get(primary) or {}
    reasons: list[str] = []
    evidence: dict = {
        "eligible_setups": setups.get("eligible_setups", []),
        "preferred_setup": primary,
        "setup": signal,
    }

    fm_vol = first_minute_volume(bars)
    evidence["first_minute_volume"] = fm_vol
    evidence["min_first_minute_volume"] = NOVA_OS_MIN_FIRST_MINUTE_VOLUME
    if fm_vol is None or fm_vol < NOVA_OS_MIN_FIRST_MINUTE_VOLUME:
        reasons.append("FIRST_MINUTE_VOLUME_LOW")
    else:
        reasons.append("FIRST_MINUTE_VOLUME_OK")

    evidence["watchlist_rank"] = watchlist_rank
    evidence["watchlist_max_rank"] = NOVA_OS_WATCHLIST_MAX_RANK
    if watchlist_rank is None or watchlist_rank < 1 or watchlist_rank > NOVA_OS_WATCHLIST_MAX_RANK:
        reasons.append("WATCHLIST_RANK_TOO_LOW")
    else:
        reasons.append("WATCHLIST_RANK_OK")

    eligible = bool(signal.get("eligible"))
    reasons.append("SETUP_MATCH" if eligible else "NO_SETUP")

    hard_fail = (
        "FIRST_MINUTE_VOLUME_LOW" in reasons
        or "WATCHLIST_RANK_TOO_LOW" in reasons
        or "NO_SETUP" in reasons
    )
    ticket = None
    if eligible and signal.get("entry_price") is not None:
        ticket = {
            "entry": signal.get("entry_price"),
            "stop": signal.get("stop_price"),
            "target": signal.get("target_price"),
        }
    return (
        GateResult(GATE_SETUP, not hard_fail, True, reasons, evidence),
        primary if eligible else None,
        ticket,
    )


def gate_ticket(ticket: dict | None) -> tuple[GateResult, dict | None]:
    if not ticket or any(ticket.get(k) is None for k in ("entry", "stop", "target")):
        return (
            GateResult(GATE_TICKET, False, True, ["TICKET_INVALID"], {"ticket": ticket}),
            None,
        )
    entry, stop, target = float(ticket["entry"]), float(ticket["stop"]), float(ticket["target"])
    ok, issues = risk_mod.validate_trade_plan(entry, stop, target)
    shares = risk_mod.position_size_shares() if ok else 0
    sized = {
        **ticket,
        "shares": shares,
        "risk_dollars": round((entry - stop) * shares, 2) if shares else None,
        "r_multiple": round((target - entry) / (entry - stop), 2) if entry > stop else None,
        "issues": issues,
    }
    if not ok:
        reasons: list[str] = []
        joined = " ".join(issues).lower()
        if "profit/loss" in joined or "ratio" in joined:
            reasons.append("RR_TOO_LOW")
        if "exceeds the" in joined and "max" in joined:
            reasons.append("STOP_TOO_WIDE")
        if not reasons:
            reasons.append("TICKET_INVALID")
        return GateResult(GATE_TICKET, False, True, reasons, {"ticket": sized}), None
    return GateResult(GATE_TICKET, True, True, ["TICKET_OK"], {"ticket": sized}), sized


def gate_catalyst(
    symbol: str,
    candidate: dict,
    articles: list[dict] | None,
    l2_features: dict | None,
) -> GateResult:
    verdict = evaluate_news_impact(
        symbol,
        articles,
        gap_percent=candidate.get("change_pct", candidate.get("gap_percent")),
        rel_volume=candidate.get("rel_volume"),
        l2_features=l2_features,
        newest_headline_at=candidate.get("newest_headline_at"),
    )
    evidence = {"news_impact": verdict.to_dict()}
    strong = (
        verdict.impact_class == "moved_price"
        and verdict.confidence >= NOVA_OS_CATALYST_MIN_CONFIDENCE
    )
    if strong:
        return GateResult(GATE_CATALYST, True, False, ["CATALYST_STRONG"], evidence)
    return GateResult(GATE_CATALYST, False, False, ["CATALYST_WEAK"], evidence)


def gate_microstructure() -> GateResult:
    return GateResult(
        GATE_MICROSTRUCTURE,
        True,
        False,
        ["MICROSTRUCTURE_NOT_EVALUATED"],
        {"status": "not_evaluated", "note": "Soft gate; awaits archive-tuned L2/T&S rules."},
    )
