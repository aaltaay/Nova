/** The Cryptos page's shared pieces: the card, its source label, the sparkline and the Fear & Greed gauge. */
import type { ReactNode } from 'react';
import { FEAR_GREED_ZONES } from './constants';
import { tipSource } from './tips/glossaryMarket';
import { useTip } from './tips/TipHost';
import type { SourceId, SourceStatus } from './types';

export function Card({ title, className = '', head, source, children, testId }: {
  title: string;
  className?: string;
  head?: ReactNode;
  source?: { ids: SourceId[]; label: string; sources: SourceStatus[]; now: number } | null;
  children: ReactNode;
  testId?: string;
}) {
  return (
    <section className={`cx-card ${className}`} data-testid={testId}>
      <header className="cx-card__head">
        <h3 className="cx-card__title">{title}</h3>
        {head}
        {source ? <SourceTag {...source} /> : null}
      </header>
      {children}
    </section>
  );
}

/** "CoinGecko ●": where a card's numbers come from, with its health as a dot (hover: when it last answered). */
export function SourceTag({ ids, label, sources, now }: { ids: SourceId[]; label: string; sources: SourceStatus[]; now: number }) {
  const tip = useTip();
  const mine = sources.filter((s) => ids.includes(s.id));
  const failing = mine.find((s) => s.ok === false);
  const waiting = mine.length === 0 || mine.every((s) => s.ok === null);
  const state = failing ? 'is-failing' : waiting ? 'is-waiting' : 'is-ok';
  return (
    <span className={`cx-card__source ${state}`} tabIndex={0} {...tip(() => tipSource(failing ?? mine[0], label, now))}>
      <i className="cx-card__source-dot" aria-hidden />
      {label}
    </span>
  );
}

export function Spark({ data, w = 84, h = 22, up }: { data: number[]; w?: number; h?: number; up: boolean }) {
  if (data.length < 2) return <svg className="cx-spark" width={w} height={h} aria-hidden />;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const pts = data
    .map((v, i) => `${((i / (data.length - 1)) * w).toFixed(1)},${(h - 2 - ((v - min) / (max - min || 1)) * (h - 4)).toFixed(1)}`)
    .join(' ');
  const color = up ? 'var(--nova-bid, #30d158)' : 'var(--nova-ask, #ff453a)';
  return (
    <svg className="cx-spark" width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden>
      <polyline points={`0,${h} ${pts} ${w},${h}`} fill={color} fillOpacity={0.1} stroke="none" />
      <polyline points={pts} fill="none" stroke={color} strokeWidth={1.4} strokeLinejoin="round" />
    </svg>
  );
}

export function Gauge({ value }: { value: number | null }) {
  const r = 22;
  const cx = 28;
  const cy = 27;
  const p = (a: number) => [cx + r * Math.cos(Math.PI * (1 - a)), cy - r * Math.sin(Math.PI * (1 - a))];
  const segs = FEAR_GREED_ZONES.map((z, i) => {
    const a0 = (i === 0 ? 0 : FEAR_GREED_ZONES[i - 1].to) / 100 + 0.01;
    const a1 = z.to / 100 - 0.01;
    const [x0, y0] = p(a0);
    const [x1, y1] = p(a1);
    return <path key={z.label} d={`M${x0} ${y0} A${r} ${r} 0 0 1 ${x1} ${y1}`} stroke={z.color} strokeWidth={5} fill="none" />;
  });
  const needle = value === null ? null : p(Math.min(1, Math.max(0, value / 100)));
  return (
    <svg width={56} height={32} viewBox="0 0 56 32" aria-hidden className="cx-gauge">
      {segs}
      {needle ? (
        <>
          <line x1={cx} y1={cy} x2={cx + (needle[0] - cx) * 0.7} y2={cy + (needle[1] - cy) * 0.7} stroke="#f5f5f7" strokeWidth={2} strokeLinecap="round" />
          <circle cx={cx} cy={cy} r={2.5} fill="#f5f5f7" />
        </>
      ) : null}
    </svg>
  );
}
