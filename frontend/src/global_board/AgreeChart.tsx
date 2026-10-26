/**
 * "Do they agree?" on the Global page (ADR 060): each market placed by its pressure (across) and its index move (up),
 * sized by the money that traded, in four boxes -- bought and rose, sold and fell, and the two that disagree (amber).
 * Drawn at the size of its box (the page never scrolls); the four boxes are named outside the plot, so no market
 * covers its name.
 */
import { signedPct, usd } from '../world_board/format';
import type { Market } from './types';
import { useBox } from '../world_board/useBox';

const PAD = { left: 18, right: 10, top: 18, bottom: 26 };
const LABELLED = 8;
const AXIS_FULL_MIN_W = 420;          // narrower, the axis's full words meet the bottom boxes' names
const CHAR_W = 6.2;                   // a label's width per character, to keep it inside the chart

/** A market's name right of its dot; above it, against the chart's right edge, when the right has no room. */
function Label({ m, cx, cy, r, W }: { m: Market; cx: number; cy: number; r: number; W: number }) {
  if (cx + r + 3 + m.exchange.length * CHAR_W <= W - PAD.right) {
    return <text className="gb-agree__label" x={cx + r + 3} y={cy + 4}>{m.exchange}</text>;
  }
  const y = cy - r - 4 >= PAD.top + 8 ? cy - r - 4 : cy + r + 12;
  return <text className="gb-agree__label" x={Math.min(cx + r, W - PAD.right)} y={y} textAnchor="end">{m.exchange}</text>;
}

export function AgreeChart({ markets }: { markets: Market[] }) {
  const [ref, { width: W, height: H }] = useBox<HTMLDivElement>({ width: 440, height: 250 });
  const known = markets.filter((m) => m.flow.pressure_pct != null && m.move.pct != null);
  const xMax = Math.max(10, ...known.map((m) => Math.abs(m.flow.pressure_pct ?? 0))) * 1.12;
  const yMax = Math.max(0.5, ...known.map((m) => Math.abs(m.move.pct ?? 0))) * 1.18;
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const x = (v: number) => PAD.left + ((v + xMax) / (2 * xMax)) * plotW;
  const y = (v: number) => PAD.top + ((yMax - v) / (2 * yMax)) * plotH;
  const maxTraded = Math.max(1, ...known.map((m) => m.flow.traded_usd ?? 0));
  const radius = (m: Market) => (m.flow.traded_usd ? Math.max(4, 15 * Math.sqrt(m.flow.traded_usd / maxTraded)) : 4);
  const labelled = new Set([...known].sort((a, b) => (b.flow.traded_usd ?? 0) - (a.flow.traded_usd ?? 0))
    .slice(0, LABELLED).map((m) => m.id));
  return (
    <div className="gb-chart" ref={ref}>
      <svg className="gb-agree" width={W} height={H} viewBox={`0 0 ${W} ${H}`} data-testid="global-agree" role="img"
        aria-label="Each market's pressure against its index move">
        <line className="gb-agree__axis" x1={x(0)} x2={x(0)} y1={PAD.top} y2={H - PAD.bottom} />
        <line className="gb-agree__axis" x1={PAD.left} x2={W - PAD.right} y1={y(0)} y2={y(0)} />
        <text className="gb-agree__q is-up" x={W - PAD.right - 4} y={PAD.top - 6} textAnchor="end">Bought &amp; rose</text>
        <text className="gb-agree__q is-down" x={PAD.left + 4} y={H - 6}>Sold &amp; fell</text>
        <text className="gb-agree__q is-warn" x={PAD.left + 4} y={PAD.top - 6}>Sold, still rose</text>
        <text className="gb-agree__q is-warn" x={W - PAD.right - 4} y={H - 6} textAnchor="end">Bought, still fell</text>
        {[...known].sort((a, b) => radius(b) - radius(a)).map((m) => {
          const p = m.flow.pressure_pct ?? 0;
          const v = m.move.pct ?? 0;
          const tone = m.mixed ? 'warn' : p >= 0 ? 'up' : 'down';
          return (
            <g key={m.id} data-testid={`global-agree-${m.id}`}>
              <circle className={`gb-agree__dot is-${tone}`} cx={x(p)} cy={y(v)} r={radius(m)}>
                <title>{`${m.exchange}: pressure ${signedPct(p)} (${usd(m.flow.pressure_usd, true)}), index ${signedPct(v, 2)}`}</title>
              </circle>
              {labelled.has(m.id) ? <Label m={m} cx={x(p)} cy={y(v)} r={radius(m)} W={W} /> : null}
            </g>
          );
        })}
        <text className="gb-agree__axislabel" x={W / 2} y={H - 6} textAnchor="middle">
          {W >= AXIS_FULL_MIN_W ? 'pressure → buyers more eager' : 'pressure →'}
        </text>
      </svg>
    </div>
  );
}
