/**
 * "Follow the sun" on the Global page (ADR 060): the last 24 hours of pressure, an hour a bar, in dollars, under each
 * region's trading hours, with a line at now. The backend sums every market's one-minute bars inside its own session.
 */
import { REGION_ORDER, REGION_SHORT } from './constants';
import { etTime, usd } from './format';
import type { RegionId, Sun } from './types';

const W = 560;
const LEFT = 64;
const PLOT = W - LEFT - 8;
const ROW = 16;
const BARS_TOP = REGION_ORDER.length * (ROW + 4) + 14;
const BARS_H = 120;

export function FollowTheSun({ sun }: { sun: Sun }) {
  const span = sun.to - sun.from;
  const x = (t: number) => LEFT + ((t - sun.from) / span) * PLOT;
  const mid = BARS_TOP + BARS_H / 2;
  const peak = Math.max(1, ...sun.hours.map((h) => Math.abs(h.net_usd)));
  const scale = (BARS_H / 2 - 4) / peak;
  const hourW = PLOT / Math.max(1, sun.hours.length);
  const ticks = sun.hours.filter((_h, i) => i % 6 === 0).map((h) => h.t).concat(sun.to);
  const regionOrder: RegionId[] = ['asia_pacific', 'middle_east_africa', 'europe', 'americas'];
  return (
    <svg className="gb-sun" viewBox={`0 0 ${W} ${BARS_TOP + BARS_H + 24}`} data-testid="global-sun"
      role="img" aria-label="Pressure per hour over the last 24 hours">
      {regionOrder.map((rid, i) => {
        const y = i * (ROW + 4);
        return (
          <g key={rid}>
            <text className="gb-sun__label" x={LEFT - 8} y={y + 12} textAnchor="end">{REGION_SHORT[rid]}</text>
            <rect className="gb-sun__track" x={LEFT} y={y} width={PLOT} height={ROW} rx={4} />
            {sun.sessions.filter((s) => s.region === rid).map((s) => (
              <rect key={`${s.market}-${s.start}`} className={`gb-sun__session${s.end <= sun.now ? ' is-past' : ''}`}
                x={x(s.start)} y={y + 2} width={Math.max(1, x(s.end) - x(s.start))} height={ROW - 4} rx={3}>
                <title>{`${s.market.toUpperCase()} ${etTime(s.start)}-${etTime(s.end)} ET`}</title>
              </rect>
            ))}
          </g>
        );
      })}
      <text className="gb-sun__label" x={LEFT - 8} y={mid + 4} textAnchor="end">Pressure</text>
      <line className="gb-sun__zero" x1={LEFT} x2={LEFT + PLOT} y1={mid} y2={mid} />
      {sun.hours.map((h) => {
        const height = Math.abs(h.net_usd) * scale;
        const regions = REGION_ORDER.filter((r) => h.by_region[r] != null)
          .map((r) => `${REGION_SHORT[r]} ${usd(h.by_region[r] ?? null, true)}`).join(', ');
        return (
          <rect key={h.t} className={`gb-sun__bar is-${h.net_usd >= 0 ? 'up' : 'down'}${h.t + 3600 > sun.now ? ' is-forming' : ''}`}
            x={x(h.t) + 1.5} width={Math.max(1, hourW - 3)} y={h.net_usd >= 0 ? mid - height : mid} height={height} rx={2}>
            <title>{`${etTime(h.t)} ET: ${usd(h.net_usd, true)} pressure of ${usd(h.traded_usd)} traded${regions ? ` (${regions})` : ''}`}</title>
          </rect>
        );
      })}
      {ticks.map((t) => (
        <text key={t} className="gb-sun__tick" x={x(t)} y={BARS_TOP + BARS_H + 16} textAnchor="middle">{etTime(t)}</text>
      ))}
      <line className="gb-sun__now" x1={x(sun.now)} x2={x(sun.now)} y1={0} y2={BARS_TOP + BARS_H + 2} />
    </svg>
  );
}
