/**
 * "Follow the sun" on the Forex page (ADR 062, mockup v2): each currency hour by hour through the FX day (from 17:00
 * New York), under the Asia, London and New York sessions with their desks' share of all forex, and a line at now.
 * A cell is the currency's strength change that hour, or its futures pressure (the switch): green stronger / bought,
 * red weaker / sold, deeper the more. Hours still to come are empty. Drawn at the size of its box (the page never
 * scrolls): the session rows take up to 12 px each, the currency rows share the rest.
 */
import { etTime, signedPct } from '../world_board/format';
import { useBox } from '../world_board/useBox';
import { SUN_FULL_FUTURES, SUN_FULL_STRENGTH } from './constants';
import type { ColorBy, Sun } from './types';

const LEFT = 92;
const RIGHT = 14;                     // room for the last hour's label
const TRACK_MAX = 12;
const GAP = 3;
const TICKS_H = 16;

/** The rows, strongest today first: the sum of each currency's hourly changes is its strength now. */
export function sunRows(sun: Sun, colorBy: ColorBy): string[] {
  const total: Record<string, number> = {};
  for (const h of sun.hours) {
    for (const [code, v] of Object.entries(colorBy === 'strength' ? h.strength : h.futures)) {
      total[code] = (total[code] ?? 0) + v;
    }
  }
  const codes = Object.keys(total);
  if (colorBy === 'futures') return ['USD', ...codes.filter((c) => c !== 'USD').sort()].filter((c) => c in total);
  return codes.sort((a, b) => total[b] - total[a]);
}

export function FollowTheSun({ sun, colorBy }: { sun: Sun; colorBy: ColorBy }) {
  const [ref, { width: W, height: H }] = useBox<HTMLDivElement>({ width: 620, height: 230 });
  const plot = Math.max(1, W - LEFT - RIGHT);
  const cw = plot / 24;
  const rows = sunRows(sun, colorBy);
  const track = Math.max(7, Math.min(TRACK_MAX, (H - TICKS_H) * 0.06));
  const top = sun.tracks.length * (track + GAP) + 6;
  const rowH = Math.max(4, (H - TICKS_H - top) / Math.max(1, rows.length));
  const cell = Math.max(3, rowH - 1.5);
  const x = (t: number) => LEFT + ((t - sun.from) / (sun.to - sun.from)) * plot;
  const full = colorBy === 'strength' ? SUN_FULL_STRENGTH : SUN_FULL_FUTURES;
  const font = Math.min(10.5, Math.max(7.5, rowH - 1));
  const labelEvery = rowH >= 8.5 ? 1 : 2;      // a short window labels every other row; every row keeps its cells
  const base = top + rows.length * rowH;
  return (
    <div className="gb-chart" ref={ref}>
      <svg className="fx-heat" width={W} height={H} viewBox={`0 0 ${W} ${H}`} data-testid="forex-sun"
        role="img" aria-label="Each currency hour by hour through the FX day">
        {sun.tracks.map((t, i) => {
          const y = i * (track + GAP);
          return (
            <g key={t.id}>
              <text className="fx-heat__label" x={LEFT - 8} y={y + track - 2} textAnchor="end">
                {t.name} <tspan className="fx-heat__share">{Math.round(t.share_pct)}%</tspan>
              </text>
              <rect className="fx-heat__track" x={LEFT} y={y} width={plot} height={track} rx={3} />
              <rect className={`fx-heat__session${t.to <= sun.now ? ' is-past' : ''}`} x={x(t.from)} y={y + 1.5}
                width={Math.max(1, x(t.to) - x(t.from))} height={Math.max(1, track - 3)} rx={2.5}>
                <title>{`${t.name} ${etTime(t.from)}-${etTime(t.to)} ET: its desks are ${t.share_pct}% of all forex`}</title>
              </rect>
            </g>
          );
        })}
        {rows.map((code, j) => {
          const y = top + j * rowH;
          return (
            <g key={code} data-testid={`forex-sun-row-${code}`}>
              {j % labelEvery === 0 ? (
                <text className="fx-heat__code" x={LEFT - 8} y={y + cell / 2 + font * 0.35} textAnchor="end"
                  style={{ fontSize: font }}>{code}</text>
              ) : null}
              {Array.from({ length: 24 }, (_v, h) => {
                const t = sun.from + h * 3600;
                const hour = sun.hours[h];
                const cx = LEFT + h * cw + 0.7;
                const w = Math.max(1, cw - 1.4);
                if (!hour || t >= sun.now) {
                  return <rect key={h} className="fx-heat__empty" x={cx} y={y} width={w} height={cell} rx={2} />;
                }
                const v = (colorBy === 'strength' ? hour.strength : hour.futures)[code];
                if (v == null) return <rect key={h} className="fx-heat__empty" x={cx} y={y} width={w} height={cell} rx={2} />;
                const tone = v > 0 ? 'up' : v < 0 ? 'down' : 'flat';
                return (
                  <rect key={h} className={`fx-heat__cell is-${tone}${t + 3600 > sun.now ? ' is-forming' : ''}`}
                    x={cx} y={y} width={w} height={cell} rx={2}
                    style={{ fillOpacity: 0.1 + 0.9 * Math.min(1, Math.abs(v) / full) }}>
                    <title>{`${code} ${etTime(t)} ET: ${colorBy === 'strength' ? `strength ${signedPct(v, 2)}` : `futures pressure ${signedPct(v)}`}`}</title>
                  </rect>
                );
              })}
            </g>
          );
        })}
        {Array.from({ length: 9 }, (_v, i) => sun.from + i * 3 * 3600).map((t) => (
          <text key={t} className="fx-heat__tick" x={x(t)} y={base + 12} textAnchor="middle">{etTime(t)}</text>
        ))}
        <line className="fx-heat__now" x1={x(sun.now)} x2={x(sun.now)} y1={0} y2={base + 2} />
      </svg>
    </div>
  );
}
