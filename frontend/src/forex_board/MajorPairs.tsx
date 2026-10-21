/**
 * "Major pairs" on the Forex page (ADR 062, mockup v2): the eight majors' pairs, row against column, strongest first, so
 * the top right is green and the bottom left red; each cell is the pair's move over the period, worked out from the two
 * currencies' moves against the dollar (a cross rate is the ratio of the two dollar rates). Drawn at the size of its
 * box (the page never scrolls).
 */
import { usd } from '../world_board/format';
import { useBox } from '../world_board/useBox';
import { MAJORS, PAIR_FULL_PCT } from './constants';
import { cross } from './cross';
import type { Currency, Period } from './types';

const LEFT = 34;
const TOP = 16;
const NOTE_H = 22;

export function majorOrder(currencies: Currency[]): Currency[] {
  const by = new Map(currencies.map((c) => [c.code, c]));
  return MAJORS.map((code) => by.get(code)).filter((c): c is Currency => !!c)
    .sort((a, b) => (b.strength_pct ?? -Infinity) - (a.strength_pct ?? -Infinity));
}

export function MajorPairs({ currencies, period, total }: { currencies: Currency[]; period: Period; total: number }) {
  const [ref, { width: W, height: H }] = useBox<HTMLDivElement>({ width: 420, height: 220 });
  const order = majorOrder(currencies);
  const n = Math.max(1, order.length);
  const cw = Math.max(10, (W - LEFT - 2) / n);
  const ch = Math.max(10, Math.min(26, (H - TOP - NOTE_H) / n));
  const full = PAIR_FULL_PCT[period];
  // the numbers fit their cells; a cell too small for a readable number keeps its colour and says it on hover
  const font = Math.min(10.5, ch - 4, (cw - 4) / 3.4);
  const eur = currencies.find((c) => c.code === 'EUR');
  return (
    <>
      <div className="gb-chart" ref={ref}>
        <svg className="fx-grid" width={W} height={H} viewBox={`0 0 ${W} ${H}`} data-testid="forex-pairs" role="img"
          aria-label="The major pairs' moves, row against column">
          {order.map((c, i) => (
            <g key={c.code}>
              <text className="fx-grid__col" x={LEFT + i * cw + cw / 2} y={TOP - 5} textAnchor="middle">{c.code}</text>
              <text className="fx-grid__row" x={LEFT - 6} y={TOP + i * ch + ch / 2 + 3.5} textAnchor="end">{c.code}</text>
            </g>
          ))}
          {order.map((a, i) => order.map((b, j) => {
            const x0 = LEFT + j * cw + 1;
            const y0 = TOP + i * ch + 1;
            if (a.code === b.code) {
              return <rect key={`${a.code}${b.code}`} className="fx-grid__self" x={x0} y={y0} width={cw - 2} height={ch - 2} rx={3} />;
            }
            const ra = a.price.vs_usd_pct;
            const rb = b.price.vs_usd_pct;
            const v = ra != null && rb != null ? cross(ra, rb) : null;
            const tone = v == null ? 'none' : v > 0 ? 'up' : v < 0 ? 'down' : 'flat';
            return (
              <g key={`${a.code}${b.code}`} data-testid={`forex-pair-${a.code}${b.code}`}>
                <rect className={`fx-grid__cell is-${tone}`} x={x0} y={y0} width={cw - 2} height={ch - 2} rx={3}
                  style={{ fillOpacity: v == null ? 0.05 : 0.1 + 0.75 * Math.min(1, Math.abs(v) / full) }}>
                  <title>{`${a.code}/${b.code}: ${v == null ? 'no price' : `${v > 0 ? '+' : ''}${v.toFixed(2)}%`}`}</title>
                </rect>
                {font >= 7 ? (
                  <text className="fx-grid__v" x={x0 + (cw - 2) / 2} y={y0 + ch / 2 + font * 0.32} textAnchor="middle"
                    style={{ fontSize: font }}>
                    {v == null ? '--' : `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(2)}`}
                  </text>
                ) : null}
              </g>
            );
          }))}
        </svg>
      </div>
      {eur ? (
        <p className="fx-note">
          {eur.size.pair} alone trades {usd(eur.size.pair_usd)} a day, {Math.round((eur.size.pair_usd / total) * 100)}% of all
          forex (BIS).
        </p>
      ) : null}
    </>
  );
}
