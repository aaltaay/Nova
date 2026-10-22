/**
 * "How late trades show up" (ADR 066, PNG v1): this year's trades by days from the trade to its report, five days a
 * bar, with the law's 45-day limit drawn; the typical wait, the share public within a week and past the limit.
 */
import { HOW_LATE_HELP } from './constants';
import type { Lag } from './types';

export function LagCard({ lag }: { lag: Lag }) {
  const w = 600;
  const h = 70;
  const top = Math.max(1, ...lag.buckets);
  const bw = w / lag.buckets.length;
  const limitX = (lag.limit_days / lag.bucket_days) * bw;
  const color = (i: number) => (i * lag.bucket_days < 30 ? 'var(--cg-up)' : i * lag.bucket_days < lag.limit_days ? 'var(--cg-warn)' : 'var(--cg-down)');
  const ticks: [number, string][] = [[0, '0'], [6, '30 d'], [12, '60 d'], [18, '90 d'], [lag.buckets.length - 1, `${(lag.buckets.length - 1) * lag.bucket_days}+ d`]];
  return (
    <section className="cg-card cg-lagc" data-testid="congress-lag" title={HOW_LATE_HELP}>
      <div className="cg-card__head">
        <h3 className="cg-card__title">How late trades show up</h3>
        <span className="cg-card__source">every trade reported this year</span>
      </div>
      <div className="cg-lagc__big">
        <div><b>{lag.median_days != null ? `${Math.round(lag.median_days)} days` : '–'}</b>typical wait</div>
        <div><b>{lag.within_week_pct != null ? `${Math.round(lag.within_week_pct)}%` : '–'}</b>within a week</div>
        <div><b className="is-down">{lag.after_limit_pct != null ? `${Math.round(lag.after_limit_pct)}%` : '–'}</b>after the limit</div>
      </div>
      <svg className="cg-lagc__svg" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" role="img"
        aria-label="days from trade to report">
        {lag.buckets.map((n, i) => {
          const bh = n ? Math.max(1.5, ((h - 16) * n) / top) : 0;
          return <rect key={i} x={i * bw + 1} y={h - 14 - bh} width={bw - 2} height={bh} rx={1.5} fill={color(i)} fillOpacity={0.85} />;
        })}
        <line x1={limitX} x2={limitX} y1={0} y2={h - 14} stroke="var(--nova-text, #f5f5f7)" strokeDasharray="2 3" />
        <text x={limitX + 5} y={10} className="cg-svg-text">{lag.limit_days}-day legal limit</text>
        {ticks.map(([i, label]) => (
          <text key={label} x={i * bw + (i === 0 ? 0 : bw / 2)} y={h - 1} className="cg-svg-text cg-svg-muted"
            textAnchor={i === 0 ? 'start' : i === lag.buckets.length - 1 ? 'end' : 'middle'}>{label}</text>
        ))}
      </svg>
    </section>
  );
}
