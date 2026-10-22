/**
 * "Most active" (ADR 066, PNG v1): the last 120 days' busiest members -- trades bought up, sold down, week by week --
 * and how long after a trade they typically report it. Click a member for their page.
 */
import { Face, PartyBadge } from './Face';
import { chamberWord, lagClass, seat } from './format';
import type { Active, Weeks } from './types';

/** Weekly bars: buys above the line (green), sells below (red). */
export function WeekBars({ weeks, width = 150, height = 30 }: { weeks: Weeks; width?: number; height?: number }) {
  const top = Math.max(1, ...weeks.buy, ...weeks.sell);
  const n = weeks.buy.length || 1;
  const bw = width / n;
  const mid = height / 2;
  return (
    <svg className="cg-weeks" width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden>
      <line x1={0} x2={width} y1={mid} y2={mid} stroke="rgba(255,255,255,.16)" />
      {weeks.buy.map((b, i) =>
        b ? <rect key={`b${i}`} x={i * bw + 1} y={mid - Math.max(1.5, ((mid - 1) * b) / top)} width={Math.max(1, bw - 2)}
          height={Math.max(1.5, ((mid - 1) * b) / top)} rx={1} fill="var(--cg-up)" /> : null,
      )}
      {weeks.sell.map((s, i) =>
        s ? <rect key={`s${i}`} x={i * bw + 1} y={mid} width={Math.max(1, bw - 2)} height={Math.max(1.5, ((mid - 1) * s) / top)}
          rx={1} fill="var(--cg-down)" /> : null,
      )}
    </svg>
  );
}

export function MostActive({ rows, total, onOpen, onAll }: {
  rows: Active[];
  total: number;
  onOpen: (bioguide: string) => void;
  onAll: () => void;
}) {
  return (
    <section className="cg-card cg-list cg-active" data-testid="congress-most-active">
      <div className="cg-card__head">
        <h3 className="cg-card__title">Most active</h3>
        <span className="cg-muted cg-small">last 120 days · bought up, sold down</span>
        <button type="button" className="cg-link cg-push" onClick={onAll} data-testid="congress-all-members">All {total} ›</button>
      </div>
      {rows.length === 0 ? <p className="cg-muted cg-empty">No trades reported in the last 120 days.</p> : null}
      {rows.map((a) => (
        <div key={a.bioguide} className="cg-ar is-clickable" role="button" tabIndex={0} onClick={() => onOpen(a.bioguide)}
          onKeyDown={(e) => { if (e.key === 'Enter') onOpen(a.bioguide); }} data-testid={`congress-active-${a.bioguide}`}>
          <Face member={a} size={34} />
          <div className="cg-ar__who">
            <div className="cg-ar__name">{a.name}<PartyBadge party={a.party} size={16} /></div>
            <div className="cg-muted cg-small">
              {seat(a)} · {chamberWord(a.chamber)}{a.left ? <span className="cg-left"> · left {a.left}</span> : null}
            </div>
          </div>
          <WeekBars weeks={a.weeks} />
          <div className="cg-ar__n"><b>{a.trades.toLocaleString()}</b><small>trades</small></div>
          <span className={`cg-pill ${lagClass(a.median_lag_days)}`}
            title="typical days from a trade to its report">~{a.median_lag_days != null ? Math.round(a.median_lag_days) : '–'} d</span>
        </div>
      ))}
    </section>
  );
}
