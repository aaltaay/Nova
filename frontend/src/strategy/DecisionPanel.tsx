/** DecisionPanel — gate-by-gate Nova OS audit (signal only; never places orders). */
import { useEffect, useRef } from 'react';
import { NOVA_OS_DECISION_LABELS, SETUP_LABELS, SYMBOL_DOUBLE_CLICK_MS } from '../constants';
import { createClickVsDoubleClick } from '../utils/clickVsDoubleClick';
import {
  attentionKindForDecision,
  pushNovaOsAttention,
} from './novaOsAttention';
import {
  decisionClass,
  firstFailedGate,
  NovaOsVerdictDetail,
} from './NovaOsVerdictDetail';
import type { NovaOsDecision } from './types';
import { useNovaOsDecide } from './useNovaOsDecide';

function DecisionCard({
  decision,
  selected,
  onSelect,
  onOpenTrading,
}: {
  decision: NovaOsDecision;
  selected: boolean;
  onSelect: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
}) {
  const failed = firstFailedGate(decision.gates);
  const symbolRef = useRef(decision.symbol);
  const onSelectRef = useRef(onSelect);
  const onOpenRef = useRef(onOpenTrading);
  symbolRef.current = decision.symbol;
  onSelectRef.current = onSelect;
  onOpenRef.current = onOpenTrading;

  const handlersRef = useRef(
    createClickVsDoubleClick(
      () => onSelectRef.current(symbolRef.current),
      () => onOpenRef.current(symbolRef.current),
      SYMBOL_DOUBLE_CLICK_MS,
    ),
  );

  useEffect(() => () => handlersRef.current.cancel(), []);

  return (
    <button
      type="button"
      className={`nova-os-decision-card ${selected ? 'selected' : ''} ${decisionClass(decision.decision)}`}
      onClick={() => handlersRef.current.handleClick()}
      title="Click: Quote Panel · Double-click: Trader (new window)"
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
          <>
            {' '}
            · first fail: <em>{failed.name}</em>
          </>
        )}
      </div>
    </button>
  );
}

interface DecisionPanelProps {
  active: boolean;
  selectedSymbol: string | null;
  onSelectSymbol: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
}

export function DecisionPanel({
  active,
  selectedSymbol,
  onSelectSymbol,
  onOpenTrading,
}: DecisionPanelProps) {
  const { decisions, selected, loading, error, dataErrors, refresh } = useNovaOsDecide(
    active,
    selectedSymbol,
  );
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
      <div className="watchlist-description">
        Nova OS gate audit for the top watchlist names
        {selectedSymbol ? ` (focus: ${selectedSymbol})` : ''}.
        Signal only — this panel never places, stages, or cancels orders.
        {' '}
        <button type="button" className="linkish" onClick={refresh}>
          Refresh
        </button>
      </div>
      {error && <div className="empty-state">{error}</div>}
      {!error && dataErrors.length > 0 && (
        <div className="empty-state nova-os-data-errors" role="alert">
          Bars unavailable for {dataErrors.map((d) => d.symbol).join(', ')} — decision skipped, not
          shown as NO_BUY.
        </div>
      )}
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
                onOpenTrading={onOpenTrading}
              />
            ))}
            {selected && !decisions.some((d) => d.symbol === selected.symbol) && (
              <DecisionCard
                decision={selected}
                selected
                onSelect={onSelectSymbol}
                onOpenTrading={onOpenTrading}
              />
            )}
          </div>
          {focus && <NovaOsVerdictDetail decision={focus} />}
        </div>
      )}
    </div>
  );
}
