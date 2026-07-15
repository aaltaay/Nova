"""
Nova OS `decide()` — ordered decision gates (Phase P2).

Composes existing strategy/news/risk modules into one auditable verdict:
  BUY | WAIT | NO_BUY with reason codes, ticket, confidence, and a receipt.

Hard gates fail → NO_BUY. Soft catalyst may downgrade BUY → WAIT. Gate 5
microstructure is a documented placeholder until archive days exist to tune it.

decide() itself NEVER places, modifies, or cancels an order — that stays true
in every mode. `would_execute` instead answers "if this decision were routed
through strategy.executor.on_signal() at `mode` right now, would something
happen (stage a ticket or place a paper bracket)?" — True for a BUY decision
whenever the effective mode is anything other than `signal`; False for
WAIT/NO_BUY or when the effective mode is `signal` (display only). A caller
that only ever calls decide() and never wires it to on_signal() will still
see would_execute=True for an auto_paper BUY — that is the truthful contract:
it describes what WOULD happen, not what decide() itself does.

Every call (unless `record=False`) writes one append-only receipt.
"""
from __future__ import annotations

from dataclasses import dataclass

from constants import (
    NOVA_OS_ACTION_DECLINED,
    NOVA_OS_ACTION_DISPLAYED,
    NOVA_OS_ACTION_HALTED,
    NOVA_OS_CITATIONS,
    NOVA_OS_DECISION_BUY,
    NOVA_OS_DECISION_NO_BUY,
    NOVA_OS_DECISION_WAIT,
    NOVA_OS_DEFAULT_MODE,
    NOVA_OS_MODE_SIGNAL,
    NOVA_OS_PRIMARY_SETUP,
)
from nova_os import codes
from nova_os.events import KIND_DECISION, record_receipt
from nova_os.gates import (
    GateResult,
    first_minute_volume,
    gate_catalyst,
    gate_microstructure,
    gate_pillars,
    gate_session,
    gate_setup,
    gate_ticket,
)
from strategy import risk as risk_mod

# Re-export for tests / callers that import helpers from decide
__all__ = ("NovaOsDecision", "decide", "first_minute_volume", "GateResult")


@dataclass
class NovaOsDecision:
    symbol: str
    decision: str
    reason_codes: list[str]
    mode: str
    requested_mode: str
    setup: str | None
    ticket: dict | None
    confidence: float
    gates: list[GateResult]
    citations: tuple[str, ...]
    would_execute: bool
    policy_version: str
    receipt: dict

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "decision": self.decision,
            "reason_codes": list(self.reason_codes),
            "mode": self.mode,
            "requested_mode": self.requested_mode,
            "setup": self.setup,
            "ticket": self.ticket,
            "confidence": self.confidence,
            "gates": [g.to_dict() for g in self.gates],
            "citations": list(self.citations),
            "would_execute": self.would_execute,
            "executed": False,
            "policy_version": self.policy_version,
            "receipt": self.receipt,
            "note": "Signal only. decide() never places, modifies, or cancels orders.",
        }


def decide(
    candidate: dict,
    bars: list[dict] | None = None,
    *,
    mode: str | None = None,
    watchlist_rank: int | None = None,
    articles: list[dict] | None = None,
    l2_features: dict | None = None,
    technical_breakout: bool = False,
    preferred_setup: str = NOVA_OS_PRIMARY_SETUP,
    record: bool = True,
) -> NovaOsDecision:
    """Run ordered gates and return an auditable decision (signal-only in P2)."""
    symbol = str(candidate.get("symbol", "?")).upper()
    bars = bars or []
    requested_mode = mode or NOVA_OS_DEFAULT_MODE
    if not codes.is_valid_mode(requested_mode):
        raise ValueError(f"unknown Nova OS mode: {requested_mode!r}")

    risk_state = risk_mod.get_state()
    gates: list[GateResult] = []
    all_reasons: list[str] = []

    g0, effective_mode, early = gate_session(risk_state, requested_mode)
    gates.append(g0)
    all_reasons.extend(early)
    if not g0.passed:
        return _finalize(
            symbol, NOVA_OS_DECISION_NO_BUY, all_reasons, gates, None, None,
            0.0, requested_mode, effective_mode, record,
        )

    g1 = gate_pillars(candidate, technical_breakout)
    gates.append(g1)
    all_reasons.extend(g1.reason_codes)
    if not g1.passed:
        return _finalize(
            symbol, NOVA_OS_DECISION_NO_BUY, all_reasons, gates, None, None,
            0.1, requested_mode, effective_mode, record,
        )

    g2, setup_name, raw_ticket = gate_setup(candidate, bars, watchlist_rank, preferred_setup)
    gates.append(g2)
    all_reasons.extend(g2.reason_codes)
    if not g2.passed:
        return _finalize(
            symbol, NOVA_OS_DECISION_NO_BUY, all_reasons, gates, setup_name, None,
            0.2, requested_mode, effective_mode, record,
        )

    g3, sized_ticket = gate_ticket(raw_ticket)
    gates.append(g3)
    all_reasons.extend(g3.reason_codes)
    if not g3.passed:
        return _finalize(
            symbol, NOVA_OS_DECISION_NO_BUY, all_reasons, gates, setup_name, sized_ticket,
            0.3, requested_mode, effective_mode, record,
        )

    g4 = gate_catalyst(symbol, candidate, articles, l2_features)
    gates.append(g4)
    all_reasons.extend(g4.reason_codes)

    g5 = gate_microstructure()
    gates.append(g5)
    all_reasons.extend(g5.reason_codes)

    if g4.passed:
        all_reasons.append("ALL_GATES_PASS")
        conf = min(0.95, 0.55 + float(g4.evidence["news_impact"]["confidence"]) * 0.4)
        return _finalize(
            symbol, NOVA_OS_DECISION_BUY, all_reasons, gates, setup_name, sized_ticket,
            conf, requested_mode, effective_mode, record,
        )

    return _finalize(
        symbol, NOVA_OS_DECISION_WAIT, all_reasons, gates, setup_name, sized_ticket,
        0.45, requested_mode, effective_mode, record,
    )


def _action_for(decision: str, reason_codes: list[str]) -> str:
    if "RISK_HALTED" in reason_codes or "LOSS_POLICY_HALT" in reason_codes:
        return NOVA_OS_ACTION_HALTED
    if decision == NOVA_OS_DECISION_BUY:
        return NOVA_OS_ACTION_DISPLAYED
    return NOVA_OS_ACTION_DECLINED


def _finalize(
    symbol: str,
    decision: str,
    reason_codes: list[str],
    gates: list[GateResult],
    setup: str | None,
    ticket: dict | None,
    confidence: float,
    requested_mode: str,
    effective_mode: str,
    record: bool,
) -> NovaOsDecision:
    seen: set[str] = set()
    unique: list[str] = []
    for r in reason_codes:
        if r not in seen:
            seen.add(r)
            unique.append(r)

    # Truthful "would something happen downstream" flag — NOT whether decide()
    # itself executes (it never does). A BUY at any mode other than `signal`
    # would stage (confirm) or place (auto_paper/auto_live) if routed through
    # executor.on_signal(); WAIT/NO_BUY never would, regardless of mode.
    would_execute = decision == NOVA_OS_DECISION_BUY and effective_mode != NOVA_OS_MODE_SIGNAL
    action = _action_for(decision, unique)
    payload = {
        "gates": [g.to_dict() for g in gates],
        "setup": setup,
        "ticket": ticket,
        "confidence": confidence,
        "citations": list(NOVA_OS_CITATIONS),
        "requested_mode": requested_mode,
    }
    if record:
        receipt = record_receipt(
            kind=KIND_DECISION,
            symbol=symbol,
            decision=decision,
            action=action,
            mode=effective_mode,
            reason_codes=unique,
            would_execute=would_execute,
            executed=False,
            payload=payload,
        )
    else:
        receipt = {
            "id": None,
            "policy_version": codes.policy_version(),
            "kind": KIND_DECISION,
            "symbol": symbol,
            "decision": decision,
            "action": action,
            "mode": effective_mode,
            "reason_codes": unique,
            "would_execute": would_execute,
            "executed": False,
            "payload": payload,
        }
    return NovaOsDecision(
        symbol=symbol,
        decision=decision,
        reason_codes=unique,
        mode=effective_mode,
        requested_mode=requested_mode,
        setup=setup,
        ticket=ticket,
        confidence=round(confidence, 3),
        gates=gates,
        citations=NOVA_OS_CITATIONS,
        would_execute=would_execute,
        policy_version=codes.policy_version(),
        receipt=receipt,
    )
