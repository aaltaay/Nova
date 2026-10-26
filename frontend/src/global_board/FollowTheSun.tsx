/**
 * "Follow the sun" on the Global page (ADR 060): the last 24 hours of pressure, an hour a bar, in dollars, under each
 * region's trading hours, with a line at now. The backend sums every market's one-minute bars inside its own session.
 * Drawn at the size of its box (the page never scrolls): the region rows take up to 16 px each, the bars the rest.
 */
import { REGION_ORDER, REGION_SHORT } from './constants';
import { etTime, usd } from '../world_board/format';
import type { RegionId, Sun } from './types';
import { useBox } from '../world_board/useBox';

const LEFT = 64;
const RIGHT = 18;                     // room for the last hour's label
const GAP = 4;
const TICKS_H = 20;
const ROW_MIN = 9;
const ROW_MAX = 16;
const BARS_MIN = 24;

export function FollowTheSun({ sun }: { sun: Sun }) {
  const [ref, { width: W, height: H }] = useBox<HTMLDivElement>({ width: 560, height: 238 });
  const plot = Math.max(1, W - LEFT - RIGHT);
  const row = Math.max(ROW_MIN, Math.min(ROW_MAX, ((H - TICKS_H) * 0.42) / REGION_ORDER.length - GAP));
  const barsTop = REGION_ORDER.length * (row + GAP) + 10;
  const barsH = Math.max(BARS_MIN, H - TICKS_H - barsTop);
  const span = sun.to - sun.from;
  const x = (t: number) => LEFT + ((t - sun.from) / span) * plot;
  const mid = barsTop + barsH / 2;
  const peak = Math.max(1, ...sun.hours.map((h) => Math.abs(h.net_usd)));
  const scale = (barsH / 2 - 4) / peak;
  const hourW = plot / Math.max(1, sun.hours.length);
  const ticks = sun.hours.filter((_h, i) => i % 6 === 0).map((h) => h.t).concat(sun.to);
  const regionOrder: RegionId[] = ['asia_pacific', 'middle_east_africa', 'europe', 'americas'];
  return (
    <div className="gb-chart" ref={ref}>
      <svg className="gb-sun" width={W} height={H} viewBox={`0 0 ${W} ${H}`} data-testid="global-sun"
        role="img" aria-label="Pressure per hour over the last 24 hours">
        {regionOrder.map((rid, i) => {
          const y = i * (row + GAP);
          return (
            <g key={rid}>
              <text className="gb-sun__label" x={LEFT - 8} y={y + row / 2 + 4} textAnchor="end">{REGION_SHORT[rid]}</text>
              <rect className="gb-sun__track" x={LEFT} y={y} width={plot} height={row} rx={4} />
              {sun.sessions.filter((s) => s.region === rid).map((s) => (
                <rect key={`${s.market}-${s.start}`} className={`gb-sun__session${s.end <= sun.now ? ' is-past' : ''}`}
                  x={x(s.start)} y={y + 2} width={Math.max(1, x(s.end) - x(s.start))} height={row - 4} rx={3}>
                  <title>{`${s.market.toUpperCase()} ${etTime(s.start)}-${etTime(s.end)} ET`}</title>
                </rect>
              ))}
            </g>
          );
        })}
        <text className="gb-sun__label" x={LEFT - 8} y={mid + 4} textAnchor="end">Pressure</text>
        <line className="gb-sun__zero" x1={LEFT} x2={LEFT + plot} y1={mid} y2={mid} />
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
          <text key={t} className="gb-sun__tick" x={x(t)} y={barsTop + barsH + 15} textAnchor="middle">{etTime(t)}</text>
        ))}
        <line className="gb-sun__now" x1={x(sun.now)} x2={x(sun.now)} y1={0} y2={barsTop + barsH + 2} />
      </svg>
    </div>
  );
}
