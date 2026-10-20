/**
 * The Global page's world map (ADR 060): one bubble per market at its exchange's city, sized by the money that traded
 * in what the row reads, coloured by its pressure or its index move (the switch), a dashed ring while it is open.
 * Hover or focus a bubble for the market's card. The map fills the box it gets (the page never scrolls); its labels
 * stay 11-13 px on screen whatever the map's scale, and the card opens beside the bubble, on the side with room.
 */
import { useMemo, type CSSProperties } from 'react';
import {
  GLOBAL_BUBBLE_MAX, GLOBAL_BUBBLE_MIN, LABEL_OFFSETS, MOVE_FULL_PCT, PRESSURE_FULL_PCT,
} from './constants';
import { signedPct, usd } from './format';
import { MarketTip } from './MarketTip';
import { project } from './project';
import type { ColorBy, Market, Period } from './types';
import { useBox, type Box } from './useBox';
import { WORLD_LAND_PATH, WORLD_VIEW } from './worldLand';

const TIP_WIDTH = 290;               // .gb-tip's outer width (border-box)
const TIP_GAP = 16;

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

/** Where the drawn map sits in its box: the view fitted whole and centred. */
export function fit(box: Box): { k: number; ox: number; oy: number } {
  const k = Math.min(box.width / WORLD_VIEW.width, box.height / WORLD_VIEW.height);
  return { k, ox: (box.width - WORLD_VIEW.width * k) / 2, oy: (box.height - WORLD_VIEW.height * k) / 2 };
}

/** The label size in view units that shows as 11-13 px on screen (12 when the map is drawn about life size). */
export function labelSize(k: number): number {
  return Math.min(Math.max(12, 11 / k), 13 / k);
}

/** The card's place in the box: right of the bubble unless that runs out of room, below its top half, above its lower. */
export function tipPlace(x: number, y: number, box: Box): CSSProperties {
  const left = x + TIP_GAP + TIP_WIDTH <= box.width ? x + TIP_GAP : Math.max(0, x - TIP_GAP - TIP_WIDTH);
  return y <= box.height / 2
    ? { left, top: Math.max(0, y - 30) }
    : { left, bottom: Math.max(0, box.height - y - 30) };
}

export function WorldMap({ markets, colorBy, period, now, hovered, onHover }: Props) {
  const maxTraded = useMemo(
    () => Math.max(0, ...markets.map((m) => m.flow.traded_usd ?? 0)),
    [markets],
  );
  const full = colorBy === 'pressure' ? PRESSURE_FULL_PCT : MOVE_FULL_PCT[period];
  // Biggest first, so a small market is never hidden under a big one.
  const order = [...markets].sort((a, b) => (b.flow.traded_usd ?? 0) - (a.flow.traded_usd ?? 0));
  const [ref, box] = useBox<HTMLDivElement>({ width: WORLD_VIEW.width, height: WORLD_VIEW.height });
  const { k, ox, oy } = fit(box);
  const font = labelSize(k);
  const tipFor = markets.find((m) => m.id === hovered) ?? null;
  const tipAt = tipFor ? project(tipFor.lon, tipFor.lat) : null;

  return (
    <div className="gb-map" data-testid="global-map" ref={ref}>
      <svg viewBox={`0 0 ${WORLD_VIEW.width} ${WORLD_VIEW.height}`} role="img"
        style={{ '--gb-map-font': `${font}px` } as CSSProperties}
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
              <text className="gb-bubble__name" x={lx} y={ly - font / 2} textAnchor={anchor}>{m.exchange}</text>
              <text className={`gb-bubble__value is-${tone}`} x={lx} y={ly + font * 0.75} textAnchor={anchor}>{value}</text>
            </g>
          );
        })}
      </svg>
      {tipFor && tipAt ? (
        <div className="gb-map__tip" style={tipPlace(ox + tipAt[0] * k, oy + tipAt[1] * k, box)}>
          <MarketTip m={tipFor} now={now} />
        </div>
      ) : null}
    </div>
  );
}
