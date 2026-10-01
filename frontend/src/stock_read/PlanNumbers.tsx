/** The plan's five numbers -- entry, stop, target, risk a share, size -- each with the rule it came
 * from. On the operator's own plan the entry and the stop are theirs to type; the risk per trade that
 * sizes every plan is the venue sleeve's (ADR 042 draft): typed here, it is saved there, and Nova's
 * automatic buys size by it too. */
import { useEffect, useState, type KeyboardEvent } from 'react';
import { parseRiskUsd, VENUE_NAMES, type SleeveRisk } from '../setups';
import { tipProps } from '../ux';
import { fmtPx, fmtStep, fmtUsd, planSubLines, sizeFor } from './planMath';
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

/** Where the risk per trade comes from and what it sizes, for its hover. */
export function riskTip(risk: SleeveRisk): string {
  const where = risk.source === 'sleeve'
    ? `The ${risk.venue ? VENUE_NAMES[risk.venue] : 'desk venue\'s'} sleeve's risk per trade: the dollars one trade `
      + 'risks. Your size is that over the risk a share, in whole shares. Nova\'s automatic buys (the bot, '
      + 'Auto-entry) and Approve size by it too, capped by the sleeve. Click to change it there.'
    : 'The dollars one trade risks. Your size is that over the risk a share, in whole shares.';
  return [where, risk.why, risk.saveError, risk.moveError].filter(Boolean).join('\n');
}

function RiskUsd({ risk, onChange }: { risk: SleeveRisk; onChange: (usd: number) => void }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(String(risk.riskUsd));
  const [bad, setBad] = useState<string | null>(null);
  const [lo, hi] = risk.bounds;
  if (editing) {
    const done = () => {
      const next = parseRiskUsd(text);
      if (next === null || next < lo || next > hi) {
        // A number the sleeve would refuse says so instead of going back silently.
        setBad(`Risk per trade is ${fmtUsd(lo)} to ${fmtUsd(hi)}: "${text}" was not saved.`);
      } else if (next !== risk.riskUsd) {
        setBad(null);
        onChange(next);
      }
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
    <>
      <button
        type="button"
        className={`sr-num__risk-usd${risk.source === 'sleeve' ? '' : ' sr-num__risk-usd--fallback'}`}
        aria-busy={risk.saving}
        onClick={() => {
          setText(String(risk.riskUsd));
          setEditing(true);
        }}
        {...tipProps(riskTip(risk), 'Risk per trade')}
        data-testid="stock-read-risk-usd"
      >
        {fmtUsd(risk.riskUsd)}{risk.saving ? '…' : ''}{risk.source === 'sleeve' ? '' : '?'}
      </button>
      {bad && <span className="sr-num__bad" data-testid="stock-read-risk-usd-bad">{bad}</span>}
    </>
  );
}

export function PlanNumbers({
  plan,
  risk,
  onRiskUsd,
  onManual,
  manualStop = null,
}: {
  plan: StockPlan;
  /** The venue sleeve's risk per trade, with where it comes from. */
  risk: SleeveRisk;
  onRiskUsd: (usd: number) => void;
  /** The operator's own plan: set by typing its entry or stop. */
  onManual: ((entry: number | null, stop: number | null) => void) | null;
  /** The stop the operator typed, kept when they move the entry (else the candles' low is used). */
  manualStop?: number | null;
}) {
  const riskUsd = risk.riskUsd;
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
          at <RiskUsd risk={risk} onChange={onRiskUsd} /> risk
          {size !== null && plan.entry !== null ? ` · ${fmtUsd(size * plan.entry)}` : ''}
        </span>
      </div>
    </div>
  );
}
