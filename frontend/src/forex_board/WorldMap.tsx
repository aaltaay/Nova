/**
 * The Forex page's world map (ADR 062, mockup v2): one bubble per currency at its home city, sized by how much of it
 * trades a day (the BIS survey's), coloured by its strength or its futures pressure (the switch), a dashed ring while
 * its home session is open. A currency IBKR does not price is drawn dashed and grey. Hover or focus a bubble for its
 * card. The map fills its box (the page never scrolls); its labels stay 11-13 px on screen.
 */
import { useMemo, type CSSProperties } from 'react';
import { fit, labelSize, tipPlace } from '../world_board/mapFit';
import { project } from '../world_board/project';
import { signedPct, usd } from '../world_board/format';
import { useBox } from '../world_board/useBox';
import { WORLD_LAND_PATH, WORLD_VIEW } from '../world_board/worldLand';
import {
  FOREX_BUBBLE_MAX, FOREX_BUBBLE_MIN, FUTURES_FULL_PCT, LABEL_OFFSETS, STRENGTH_FULL_PCT,
} from './constants';
import { CurrencyTip } from './CurrencyTip';
import type { ColorBy, Currency, Period } from './types';

const TIP_WIDTH = 330;               // .fx-tip's outer width (border-box)

interface Props {
  currencies: Currency[];
  colorBy: ColorBy;
  period: Period;
  now: number;
  asOf: string;
  hovered: string | null;
  onHover: (code: string | null) => void;
}

export function colorValue(c: Currency, colorBy: ColorBy): number | null {
  return colorBy === 'strength' ? c.strength_pct : c.futures.pressure_pct;
}

/** The label under a currency's code: its strength, or its futures money. */
export function valueWord(c: Currency, colorBy: ColorBy): string {
  if (colorBy === 'strength') return c.strength_pct == null ? 'no price' : signedPct(c.strength_pct, 2);
  return c.futures.pressure_usd != null ? usd(c.futures.pressure_usd, true) : 'no futures';
}

export function WorldMap({ currencies, colorBy, period, now, asOf, hovered, onHover }: Props) {
  const maxSize = useMemo(() => Math.max(1, ...currencies.map((c) => c.size.usd)), [currencies]);
  const full = colorBy === 'strength' ? STRENGTH_FULL_PCT[period] : FUTURES_FULL_PCT;
  const order = [...currencies].sort((a, b) => b.size.usd - a.size.usd);   // biggest first: small ones on top
  const [ref, box] = useBox<HTMLDivElement>({ width: WORLD_VIEW.width, height: WORLD_VIEW.height });
  const { k, ox, oy } = fit(box);
  const font = labelSize(k);
  const priced = currencies.filter((c) => c.strength_pct != null).length;
  const tipFor = currencies.find((c) => c.code === hovered) ?? null;
  const tipAt = tipFor ? project(tipFor.lon, tipFor.lat) : null;

  return (
    <div className="gb-map" data-testid="forex-map" ref={ref}>
      <svg viewBox={`0 0 ${WORLD_VIEW.width} ${WORLD_VIEW.height}`} role="img"
        style={{ '--gb-map-font': `${font}px` } as CSSProperties}
        aria-label="World map of every currency's size and its day">
        <path className="gb-map__land" d={WORLD_LAND_PATH} />
        {order.map((c) => {
          const [x, y] = project(c.lon, c.lat);
          const r = Math.max(FOREX_BUBBLE_MIN, FOREX_BUBBLE_MAX * Math.sqrt(c.size.usd / maxSize));
          const v = colorValue(c, colorBy);
          const tone = v == null ? 'none' : v > 0 ? 'up' : v < 0 ? 'down' : 'flat';
          const [dx, dy, anchor] = LABEL_OFFSETS[c.code] ?? [0, -r - 10, 'middle'];
          const lx = x + dx;
          const ly = y + dy;
          return (
            <g key={c.code} className={`gb-bubble is-${tone}${hovered === c.code ? ' is-hovered' : ''}`}
              data-testid={`forex-bubble-${c.code}`} tabIndex={0}
              onMouseEnter={() => onHover(c.code)} onMouseLeave={() => onHover(null)}
              onFocus={() => onHover(c.code)} onBlur={() => onHover(null)}>
              {Math.hypot(dx, dy) > r + 10 ? <line className="gb-bubble__lead" x1={x} y1={y} x2={lx} y2={ly - 4} /> : null}
              {c.home.open ? <circle className="gb-bubble__ring" cx={x} cy={y} r={r + 4} /> : null}
              <circle className="gb-bubble__dot" cx={x} cy={y} r={r}
                style={{ fillOpacity: v == null ? 0.08 : 0.2 + 0.4 * Math.min(1, Math.abs(v) / full) }} />
              <circle className="gb-bubble__hit" cx={x} cy={y} r={Math.max(r, 12)} />
              <text className="gb-bubble__name" x={lx} y={ly - font / 2} textAnchor={anchor}>
                {c.code} <tspan className="fx-size">{usd(c.size.usd)}</tspan>
              </text>
              <text className={`gb-bubble__value is-${tone}`} x={lx} y={ly + font * 0.75} textAnchor={anchor}>
                {valueWord(c, colorBy)}
              </text>
            </g>
          );
        })}
      </svg>
      {tipFor && tipAt ? (
        <div className="gb-map__tip" style={tipPlace(ox + tipAt[0] * k, oy + tipAt[1] * k, box, TIP_WIDTH)}>
          <CurrencyTip c={tipFor} now={now} period={period} priced={priced} asOf={asOf} />
        </div>
      ) : null}
    </div>
  );
}
