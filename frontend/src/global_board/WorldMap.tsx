/**
 * The Global page's world map (ADR 060): one bubble per market at its exchange's city, sized by the money that traded
 * in what the row reads, coloured by its pressure or its index move (the switch), a dashed ring while it is open.
 * Hover or focus a bubble for the market's card.
 */
import { useMemo } from 'react';
import {
  GLOBAL_BUBBLE_MAX, GLOBAL_BUBBLE_MIN, LABEL_OFFSETS, MOVE_FULL_PCT, PRESSURE_FULL_PCT,
} from './constants';
import { signedPct, usd } from './format';
import { MarketTip } from './MarketTip';
import { project } from './project';
import type { ColorBy, Market, Period } from './types';
import { WORLD_LAND_PATH, WORLD_VIEW } from './worldLand';

interface Props {
  markets: Market[];
  colorBy: ColorBy;
  period: Period;
  now: number;
  hovered: string | null;
  onHover: (id: string | null) => void;
}

export function colorValue(m: Market, colorBy: ColorBy): number | null {
  return colorBy === 'pressure' ? m.flow.pressure_pct : m.move.pct;
}

/** 0.2 .. 0.6 fill strength for a value against its full-strength scale. */
function strength(v: number, full: number): number {
  return 0.2 + 0.4 * Math.min(1, Math.abs(v) / full);
}

export function WorldMap({ markets, colorBy, period, now, hovered, onHover }: Props) {
  const maxTraded = useMemo(
    () => Math.max(0, ...markets.map((m) => m.flow.traded_usd ?? 0)),
    [markets],
  );
  const full = colorBy === 'pressure' ? PRESSURE_FULL_PCT : MOVE_FULL_PCT[period];
  // Biggest first, so a small market is never hidden under a big one.
  const order = [...markets].sort((a, b) => (b.flow.traded_usd ?? 0) - (a.flow.traded_usd ?? 0));
  const tipFor = markets.find((m) => m.id === hovered) ?? null;
  const tipAt = tipFor ? project(tipFor.lon, tipFor.lat) : null;

  return (
    <div className="gb-map" data-testid="global-map">
      <svg viewBox={`0 0 ${WORLD_VIEW.width} ${WORLD_VIEW.height}`} role="img"
        aria-label="World map of the markets' money in and out">
        <path className="gb-map__land" d={WORLD_LAND_PATH} />
        {order.map((m) => {
          const [x, y] = project(m.lon, m.lat);
          const traded = m.flow.traded_usd;
          const r = traded && maxTraded
            ? Math.max(GLOBAL_BUBBLE_MIN, GLOBAL_BUBBLE_MAX * Math.sqrt(traded / maxTraded))
            : GLOBAL_BUBBLE_MIN;
          const v = colorValue(m, colorBy);
          const tone = v == null ? 'none' : v > 0 ? 'up' : v < 0 ? 'down' : 'flat';
          const [dx, dy, anchor] = LABEL_OFFSETS[m.id] ?? [0, -r - 10, 'middle'];
          const lx = x + dx;
          const ly = y + dy;
          const open = m.session.state === 'open';
          const value = colorBy === 'pressure'
            ? (m.flow.pressure_usd != null ? usd(m.flow.pressure_usd, true) : signedPct(m.flow.pressure_pct))
            : signedPct(m.move.pct, 2);
          return (
            <g key={m.id} className={`gb-bubble is-${tone}${hovered === m.id ? ' is-hovered' : ''}`}
              data-testid={`global-bubble-${m.id}`} tabIndex={0}
              onMouseEnter={() => onHover(m.id)} onMouseLeave={() => onHover(null)}
              onFocus={() => onHover(m.id)} onBlur={() => onHover(null)}>
              {Math.hypot(dx, dy) > r + 12 ? <line className="gb-bubble__lead" x1={x} y1={y} x2={lx} y2={ly - 4} /> : null}
              {open ? <circle className="gb-bubble__ring" cx={x} cy={y} r={r + 4} /> : null}
              <circle className="gb-bubble__dot" cx={x} cy={y} r={r}
                style={{ fillOpacity: v == null ? 0.08 : strength(v, full) }} />
              <circle className="gb-bubble__hit" cx={x} cy={y} r={Math.max(r, 14)} />
              <text className="gb-bubble__name" x={lx} y={ly - 6} textAnchor={anchor}>{m.exchange}</text>
              <text className={`gb-bubble__value is-${tone}`} x={lx} y={ly + 9} textAnchor={anchor}>{value}</text>
            </g>
          );
        })}
      </svg>
      {tipFor && tipAt ? (
        <div className="gb-map__tip" style={{
          left: `${Math.min(70, Math.max(2, (tipAt[0] / WORLD_VIEW.width) * 100 - 12))}%`,
          top: `${Math.min(62, (tipAt[1] / WORLD_VIEW.height) * 100 + 7)}%`,
        }}>
          <MarketTip m={tipFor} now={now} />
        </div>
      ) : null}
    </div>
  );
}
