/** Small pieces the Market cards share: the line chart, the switches, a card frame. */
import type { ReactNode } from 'react';
import { MARKET_PERIODS, PERIOD_LABEL } from './constants';
import type { Period } from './types';

export interface SparkProps {
  /** `[t, value]` pairs (a time axis) or bare values (evenly spaced). */
  points: [number, number][] | number[];
  height: number;
  /** Time axis bounds; the line stops where the data stops (now). */
  from?: number;
  to?: number;
  /** A dotted reference line (the prior close / zero). */
  zero?: number | null;
  /** A tick at this time (the 09:30 open). */
  mark?: number | null;
  /** Colour by the last point against `zero` (else by first vs last). */
  label: string;
}

export function Spark({ points, height, from, to, zero = null, mark = null, label }: SparkProps) {
  const W = 240;
  const pairs: [number, number][] = (points as unknown[]).length && Array.isArray((points as unknown[])[0])
    ? (points as [number, number][])
    : (points as number[]).map((v, i) => [i, v] as [number, number]);
  if (pairs.length < 2) return <div className="mk-spark mk-spark--empty" style={{ height }} aria-label={`${label}: no line yet`} />;
  const t0 = from ?? pairs[0][0];
  const t1 = to ?? pairs[pairs.length - 1][0];
  const span = t1 - t0 || 1;
  const vals = pairs.map((p) => p[1]);
  const lo = Math.min(...vals, zero ?? Infinity);
  const hi = Math.max(...vals, zero ?? -Infinity);
  const pad = (hi - lo) * 0.12 || 1;
  const y = (v: number) => height - ((v - (lo - pad)) / (hi + pad - (lo - pad))) * height;
  const x = (t: number) => Math.min(W, Math.max(0, ((t - t0) / span) * W));
  const d = pairs.map(([t, v], i) => `${i ? 'L' : 'M'}${x(t).toFixed(1)} ${y(v).toFixed(1)}`).join(' ');
  const last = pairs[pairs.length - 1];
  const up = zero != null ? last[1] >= zero : last[1] >= pairs[0][1];
  const cls = up ? 'is-up' : 'is-down';
  return (
    <svg className={`mk-spark ${cls}`} viewBox={`0 0 ${W} ${height}`} preserveAspectRatio="none" style={{ height }}
      role="img" aria-label={label}>
      {zero != null ? <line className="mk-spark__zero" x1={0} x2={W} y1={y(zero)} y2={y(zero)} /> : null}
      {mark != null && mark > t0 && mark < t1 ? <line className="mk-spark__mark" x1={x(mark)} x2={x(mark)} y1={0} y2={height} /> : null}
      <path className="mk-spark__fill" d={`${d} L${x(last[0])} ${height} L${x(pairs[0][0])} ${height}Z`} />
      <path className="mk-spark__line" d={d} />
      <circle className="mk-spark__dot" cx={x(last[0])} cy={y(last[1])} r={2.4} />
    </svg>
  );
}

export function PeriodSwitch({ value, onChange, label }: { value: Period; onChange: (p: Period) => void; label: string }) {
  return (
    <span className="mk-seg" role="radiogroup" aria-label={label}>
      {MARKET_PERIODS.map((p) => (
        <button key={p} type="button" role="radio" aria-checked={p === value} className={p === value ? 'is-on' : ''}
          onClick={() => onChange(p)}>
          {PERIOD_LABEL[p]}
        </button>
      ))}
    </span>
  );
}

export function Card({ title, hint, extra, children, className = '', testId }: {
  title: string; hint?: ReactNode; extra?: ReactNode; children: ReactNode; className?: string; testId?: string;
}) {
  return (
    <section className={`mk-card ${className}`} data-testid={testId}>
      <header className="mk-card__head">
        <h3>{title}</h3>
        {extra}
        {hint ? <span className="mk-hint">{hint}</span> : null}
      </header>
      {children}
    </section>
  );
}

/** A clickable stock symbol: opens the Trader. */
export function Sym({ symbol, onOpen }: { symbol: string; onOpen?: (s: string) => void }) {
  if (!onOpen) return <span className="mk-sym">{symbol}</span>;
  return (
    <button type="button" className="mk-sym mk-sym--link" onClick={() => onOpen(symbol)} title={`Open ${symbol} in the Trader`}>
      {symbol}
    </button>
  );
}
