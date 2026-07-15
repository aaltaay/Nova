/** DecisionPanel — gate-by-gate Nova OS audit (signal only; never places orders). */
import { useEffect, useRef } from 'react';
import { NOVA_OS_DECISION_LABELS, SETUP_LABELS } from '../constants';
import {
  attentionKindForDecision,
  pushNovaOsAttention,
} from './novaOsAttention';
import { NovaOsAttentionStrip } from './NovaOsAttentionStrip';
import type { NovaOsDecision, NovaOsGateResult } from './types';
import { useNovaOsDecide } from './useNovaOsDecide';

function fmtPrice(v: number | null | undefined): string {
  return v == null ? '—' : `$${Number(v).toFixed(2)}`;
}

function decisionClass(decision: string): string {
  if (decision === 'BUY') return 'nova-os-decision-buy';
  if (decision === 'WAIT') return 'nova-os-decision-wait';
  return 'nova-os-decision-nobuy';
}

function firstFailedGate(gates: NovaOsGateResult[]): NovaOsGateResult | null {
  return gates.find((g) => !g.passed) ?? null;
}

function GateRow({ gate, highlight }: { gate: NovaOsGateResult; highlight: boolean }) {
  return (
    <li
      className={`nova-os-gate ${gate.passed ? 'nova-os-gate-pass' : 'nova-os-gate-fail'}${highlight ? ' nova-os-gate-first-fail' : ''}`}
      title={gate.reason_codes.join(', ')}
    >
      <span className="nova-os-gate-icon" aria-hidden>{gate.passed ? '✓' : '✗'}</span>
      <span className="nova-os-gate-name">{gate.name}</span>
      <span className="nova-os-gate-hard">{gate.hard ? 'hard' : 'soft'}</span>
      <span className="nova-os-gate-reasons">{gate.reason_codes.join(' · ') || '—'}</span>
    </li>
  );
}

function DecisionCard({
  decision,
  selected,
  onSelect,
}: {
  decision: NovaOsDecision;
  selected: boolean;
  onSelect: (symbol: string) => void;
}) {
  const failed = firstFailedGate(decision.gates);
  return (
    <button
      type="button"
      className={`nova-os-decision-card ${selected ? 'selected' : ''} ${decisionClass(decision.decision)}`}
      onClick={() => onSelect(decision.symbol)}
    >
      <div className="nova-os-decision-card-head">
        <strong>{decision.symbol}</strong>
        <span className={`nova-os-verdict ${decisionClass(decision.decision)}`}>
          {NOVA_OS_DECISION_LABELS[decision.decision] ?? decision.decision}
        </span>
      </div>
      <div className="nova-os-decision-card-meta">
        {decision.setup ? (SETUP_LABELS[decision.setup] ?? decision.setup) : 'no setup'}
        {' · '}
        conf {(decision.confidence * 100).toFixed(0)}%
        {failed && !decision.gates.every((g) => g.passed) && (
          <> · first fail: <em>{failed.name}</em></>
        )}
      </div>
    </button>
  );
}

function DecisionDetail({ decision }: { decision: NovaOsDecision }) {
  const failed = firstFailedGate(decision.gates);
  const ticket = decision.ticket;
  return (
    <div className="nova-os-decision-detail">
      <div className={`nova-os-verdict-banner ${decisionClass(decision.decision)}`}>
        <div>
          <strong>{decision.symbol}</strong>
          {' — '}
          {NOVA_OS_DECISION_LABELS[decision.decision] ?? decision.decision}
          <span className="na-muted"> · mode {decision.mode} · policy {decision.policy_version}</span>
        </div>
        <div className="nova-os-disclosure">
          Signal only. would_execute={String(decision.would_execute)}; executed={String(decision.executed)}.
          Nothing is placed from this panel.
        </div>
      </div>

      {failed && (
        <div className="nova-os-first-fail" role="status">
          First failing gate: <strong>{failed.name}</strong>
          {' — '}
          {failed.reason_codes.join(', ') || 'see evidence'}
        </div>
      )}

      <h4 className="nova-os-section-title">Gates</h4>
      <ul className="nova-os-gate-list">
        {decision.gates.map((g) => (
          <GateRow key={g.name} gate={g} highlight={failed?.name === g.name && !g.passed} />
        ))}
      </ul>

      <h4 className="nova-os-section-title">Ticket</h4>
      {ticket ? (
        <div className="nova-os-ticket">
          <span>Entry {fmtPrice(ticket.entry as number | null)}</span>
          <span>Stop {fmtPrice(ticket.stop as number | null)}</span>
          <span>Target {fmtPrice(ticket.target as number | null)}</span>
          <span>Shares {ticket.shares ?? '—'}</span>
          <span>R {ticket.r_multiple ?? '—'}</span>
        </div>
      ) : (
        <div className="na-muted">No ticket — a hard gate failed before sizing.</div>
      )}

      <h4 className="nova-os-section-title">Reason codes</h4>
      <div className="nova-os-reason-row">
        {decision.reason_codes.map((code) => (
          <span key={code} className="pillar-chip">{code}</span>
        ))}
      </div>

      <h4 className="nova-os-section-title">Citations</h4>
      <ul className="nova-os-citations">
        {decision.citations.map((c) => (
          <li key={c}>{c}</li>
        ))}
      </ul>

      {decision.receipt?.id != null && (
        <div className="na-muted nova-os-receipt">
          Receipt #{decision.receipt.id} · action {decision.receipt.action}
        </div>
      )}
    </div>
  );
}

interface DecisionPanelProps {
  active: boolean;
  selectedSymbol: string | null;
  onSelectSymbol: (symbol: string) => void;
}

export function DecisionPanel({ active, selectedSymbol, onSelectSymbol }: DecisionPanelProps) {
  const { decisions, selected, loading, error, refresh } = useNovaOsDecide(active, selectedSymbol);
  const seenReceipts = useRef<Set<number>>(new Set());

  useEffect(() => {
    if (!active) return;
    const pool = [...decisions];
    if (selected) pool.push(selected);
    for (const d of pool) {
      const id = d.receipt?.id;
      if (id == null || seenReceipts.current.has(id)) continue;
      seenReceipts.current.add(id);
      if (d.decision === 'BUY' || d.decision === 'WAIT') {
        pushNovaOsAttention(attentionKindForDecision(d.decision), { symbol: d.symbol });
      }
    }
  }, [active, decisions, selected]);

  const focus = selected ?? decisions[0] ?? null;

  return (
    <div className="nova-os-decision-panel">
      <NovaOsAttentionStrip />
      <div className="watchlist-description">
        Nova OS gate audit for the top watchlist names
        {selectedSymbol ? ` (focus: ${selectedSymbol})` : ''}.
        Signal only — this panel never places, stages, or cancels orders.
        {' '}
        <button type="button" className="linkish" onClick={refresh}>Refresh</button>
      </div>
      {error && <div className="empty-state">{error}</div>}
      {!error && loading && decisions.length === 0 && (
        <div className="empty-state">Loading Nova OS decisions…</div>
      )}
      {!error && !loading && decisions.length === 0 && !focus && (
        <div className="empty-state">No watchlist candidates to decide on right now.</div>
      )}
      {(decisions.length > 0 || focus) && (
        <div className="nova-os-decision-layout">
          <div className="nova-os-decision-list">
            {decisions.map((d) => (
              <DecisionCard
                key={`${d.symbol}-${d.receipt?.id ?? d.policy_version}`}
                decision={d}
                selected={focus?.symbol === d.symbol}
                onSelect={onSelectSymbol}
              />
            ))}
            {selected && !decisions.some((d) => d.symbol === selected.symbol) && (
              <DecisionCard
                decision={selected}
                selected
                onSelect={onSelectSymbol}
              />
            )}
          </div>
          {focus && <DecisionDetail decision={focus} />}
        </div>
      )}
    </div>
  );
}
