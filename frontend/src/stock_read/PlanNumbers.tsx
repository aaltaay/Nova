/** The plan's five numbers -- entry, stop, target, risk a share, size -- each with the rule it came
 * from. On the operator's own plan the entry and the stop are theirs to type; the risk per trade
 * that sizes every plan is theirs everywhere. */
import { useEffect, useState, type KeyboardEvent } from 'react';
import { tipProps } from '../ux';
import { fmtPx, fmtStep, fmtUsd, parseRiskUsd, planSubLines, sizeFor } from './planMath';
import type { StockPlan } from './types';

function parsePrice(raw: string): number | null {
  const n = Number(raw.replace(/[$,\s]/g, ''));
  return Number.isFinite(n) && n > 0 ? n : null;
}

/** A number the operator may type: commits on Enter or on leaving the field, Escape puts it back. */
export function PriceInput({
  value,
  label,
  onCommit,
  testId,
}: {
  value: number | null;
  label: string;
  onCommit: (next: number | null) => void;
  testId: string;
}) {
  const shown = value === null ? '' : fmtPx(value);
  const [text, setText] = useState(shown);
  useEffect(() => setText(shown), [shown]);
  const commit = () => {
    const next = text.trim() ? parsePrice(text) : null;
    if (text.trim() && next === null) {
      setText(shown);
      return;
    }
    if (next !== value) onCommit(next);
  };
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
    if (e.key === 'Escape') {
      setText(shown);
      (e.target as HTMLInputElement).blur();
    }
    e.stopPropagation(); // the desk's hot keys never see what is typed here
  };
  return (
    <input
      className="sr-num__input"
      inputMode="decimal"
      aria-label={label}
      placeholder="—"
      value={text}
      onChange={e => setText(e.target.value)}
      onBlur={commit}
      onKeyDown={onKey}
      data-testid={testId}
    />
  );
}

function RiskUsd({ riskUsd, onChange }: { riskUsd: number; onChange: (usd: number) => void }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(String(riskUsd));
  if (editing) {
    const done = () => {
      const next = parseRiskUsd(text);
      if (next !== null) onChange(next);
      setEditing(false);
    };
    return (
      <input
        className="sr-num__risk-input"
        inputMode="decimal"
        aria-label="Risk per trade in dollars"
        autoFocus
        value={text}
        onChange={e => setText(e.target.value)}
        onBlur={done}
        onKeyDown={e => {
          if (e.key === 'Enter') done();
          if (e.key === 'Escape') setEditing(false);
          e.stopPropagation();
        }}
        data-testid="stock-read-risk-usd-input"
      />
    );
  }
  return (
    <button
      type="button"
      className="sr-num__risk-usd"
      onClick={() => {
        setText(String(riskUsd));
        setEditing(true);
      }}
      {...tipProps('The dollars you risk on one trade. The size is that over the risk a share, in whole shares. Saved on this desk.', 'Risk per trade')}
      data-testid="stock-read-risk-usd"
    >
      {fmtUsd(riskUsd)}
    </button>
  );
}

export function PlanNumbers({
  plan,
  riskUsd,
  onRiskUsd,
  onManual,
  manualStop = null,
}: {
  plan: StockPlan;
  riskUsd: number;
  onRiskUsd: (usd: number) => void;
  /** The operator's own plan: set by typing its entry or stop. */
  onManual: ((entry: number | null, stop: number | null) => void) | null;
  /** The stop the operator typed, kept when they move the entry (else the candles' low is used). */
  manualStop?: number | null;
}) {
  const size = sizeFor(riskUsd, plan.risk);
  const sub = planSubLines(plan, riskUsd, size);
  const targetR = plan.rr === null ? '' : ` ${plan.rr.toFixed(plan.rr % 1 ? 1 : 0)}R`;
  return (
    <div className="sr-plan__nums">
      <div className="sr-num sr-num--entry" {...tipProps(plan.entry_rule, 'Entry')}>
        <span className="sr-num__k">Entry</span>
        {onManual ? (
          <PriceInput value={plan.entry} label="Your entry" testId="stock-read-entry-input"
            onCommit={v => onManual(v, v === null ? null : manualStop)} />
        ) : (
          <span className="sr-num__v" data-testid="stock-read-entry">{fmtPx(plan.entry)}</span>
        )}
        <span className="sr-num__s">{sub.entry}</span>
      </div>
      <div className="sr-num sr-num--stop" {...tipProps(plan.stop_rule, 'Stop')}>
        <span className="sr-num__k">Stop</span>
        {onManual ? (
          <PriceInput value={plan.stop} label="Your stop" testId="stock-read-stop-input"
            onCommit={v => onManual(plan.entry, v)} />
        ) : (
          <span className="sr-num__v" data-testid="stock-read-stop">{fmtPx(plan.stop)}</span>
        )}
        <span className="sr-num__s">{sub.stop}</span>
      </div>
      <div className="sr-num sr-num--target" {...tipProps(plan.target_rule, 'Target')}>
        <span className="sr-num__k">Target{targetR}</span>
        <span className="sr-num__v" data-testid="stock-read-target">{fmtPx(plan.target)}</span>
        <span className="sr-num__s">{sub.target}</span>
      </div>
      <div className="sr-num sr-num--risk">
        <span className="sr-num__k">Risk / sh</span>
        <span className="sr-num__v" data-testid="stock-read-risk">{fmtStep(plan.risk, plan.entry)}</span>
        <span className="sr-num__s">{sub.risk}</span>
      </div>
      <div className="sr-num sr-num--size">
        <span className="sr-num__k">Size</span>
        <span className="sr-num__v" data-testid="stock-read-size">{size === null ? '—' : `${size.toLocaleString('en-US')} sh`}</span>
        <span className="sr-num__s">
          at <RiskUsd riskUsd={riskUsd} onChange={onRiskUsd} /> risk
          {size !== null && plan.entry !== null ? ` · ${fmtUsd(size * plan.entry)}` : ''}
        </span>
      </div>
    </div>
  );
}
