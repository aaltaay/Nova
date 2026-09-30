/**
 * The Cryptos page's chart (ADR 040): Coinbase candles with the day's levels drawn the way the approved mockup
 * drew them -- the 24-hour high, the crypto day's open (00:00 UTC), the last trade, the 16:00 ET stock close and
 * the move since, the US stock sessions -- and a hover card on every candle and level.
 */
import { level, pct, price, timeEt, dateEt } from './format';
import { tipChartLevel, tipStockClose, tipUsBand } from './tips/glossaryMarket';
import { useTip } from './tips/TipHost';
import type { Candle, CryptoCandles } from './types';

const W = 620;
const H = 222;
const L = 4;
const R = W - 92;
const T = 16;
const B = 158;
const VT = 162;
const VB = 186;
const STEP: Record<string, number> = { '15m': 900, '1h': 3600, '4h': 14400, '1d': 86400 };

function niceStep(range: number): number {
  const raw = range / 4;
  const mag = 10 ** Math.floor(Math.log10(raw || 1));
  const n = raw / mag;
  return (n < 1.5 ? 1 : n < 2.25 ? 2 : n < 3.5 ? 2.5 : n < 7.5 ? 5 : 10) * mag;
}

function timeLabels(candles: Candle[], tf: string): { t: number; text: string }[] {
  const out: { t: number; text: string }[] = [];
  const every = tf === '4h' ? 18 : tf === '1d' ? 16 : 0;
  candles.forEach((c, i) => {
    const hm = timeEt(c.t);
    if (tf === '15m' && hm.endsWith(':00') && Number(hm.slice(0, 2)) % 4 === 0) out.push({ t: c.t, text: hm });
    else if (tf === '1h' && hm === '00:00') out.push({ t: c.t, text: new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', weekday: 'short' }).format(new Date(c.t * 1000)) });
    else if (every && i % every === 0 && i > 0) out.push({ t: c.t, text: dateEt(c.t) });
  });
  return out;
}

export function CandleChart({ data }: { data: CryptoCandles }) {
  const tip = useTip();
  const candles = data.candles;
  const step = STEP[data.tf] ?? 900;
  if (candles.length < 2) return null;
  const lv = data.levels;
  const t0 = candles[0].t;
  const t1 = candles[candles.length - 1].t + step;
  const lows = candles.map((c) => c.l);
  const highs = candles.map((c) => c.h);
  const extra = [lv.high_24h, lv.day_open, lv.stock_close?.price].filter((v): v is number => v !== null && v !== undefined);
  let lo = Math.min(...lows, ...extra.filter((v) => v >= Math.min(...lows) * 0.97));
  let hi = Math.max(...highs, ...extra.filter((v) => v <= Math.max(...highs) * 1.03));
  const pad = (hi - lo) * 0.06 || hi * 0.01;
  lo -= pad;
  hi += pad;
  const x = (t: number) => L + ((t - t0) / (t1 - t0)) * (R - L);
  const y = (p: number) => T + ((hi - p) / (hi - lo)) * (B - T);
  const cw = Math.max(1, ((R - L) / candles.length) * 0.64);
  const vMax = Math.max(...candles.map((c) => c.v ?? 0), 1e-12);
  const gridStep = niceStep(hi - lo);
  const grid: number[] = [];
  for (let g = Math.ceil(lo / gridStep) * gridStep; g < hi; g += gridStep) grid.push(g);
  const last = candles[candles.length - 1];
  const up = (data.change_24h_pct ?? last.c - candles[0].o) >= 0;

  const tags = [
    lv.high_24h !== null ? { key: 'high', p: lv.high_24h, text: `High ${level(lv.high_24h)}`, fill: '#3a3a3c', ink: '#f5f5f7' } : null,
    { key: 'last', p: last.c, text: `Last ${level(last.c)}`, fill: up ? '#30d158' : '#ff453a', ink: '#000' },
    lv.day_open !== null ? { key: 'open', p: lv.day_open, text: `Open ${level(lv.day_open)}`, fill: '#0a84ff', ink: '#fff' } : null,
  ].filter((t): t is NonNullable<typeof t> => t !== null && t.p >= lo && t.p <= hi)
    .map((t) => ({ ...t, y: y(t.p) }))
    .sort((a, b) => a.y - b.y);
  for (let i = 1; i < tags.length; i += 1) {
    if (tags[i].y - tags[i - 1].y < 17) tags[i].y = tags[i - 1].y + 17;
  }

  const regular = data.sessions.filter((s) => s.kind === 'regular');
  const lastRegular = regular[regular.length - 1];
  const sc = lv.stock_close && lv.stock_close.at >= t0 && lv.stock_close.at <= t1 ? lv.stock_close : null;
  const since = sc && data.last !== null ? pct((data.last / sc.price - 1) * 100) : null;
  const dayOpenX = lv.day_open_at !== null && lv.day_open_at >= t0 ? x(lv.day_open_at) : L;

  return (
    <svg className="cx-chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${data.symbol}, ${data.tf} candles`} data-testid="crypto-chart">
      {regular.map((s) => (
        <rect key={s.start} x={x(s.start)} y={T - 12} width={Math.max(0, x(s.end) - x(s.start))} height={VB - T + 12}
          fill="rgba(48,209,88,0.05)" {...tip(tipUsBand)} />
      ))}
      {lastRegular && x(lastRegular.end) - x(lastRegular.start) > 70 ? (
        <text x={x(lastRegular.start) + 4} y={T - 3} className="cx-chart__band">US stocks open</text>
      ) : null}
      {grid.map((g) => (
        <g key={g}>
          <line x1={L} x2={R} y1={y(g)} y2={y(g)} stroke="rgba(255,255,255,0.06)" />
          {tags.every((t) => Math.abs(t.y - y(g)) > 12) ? (
            <text x={R + 6} y={y(g) + 3.5} className="cx-chart__axis">{level(g)}</text>
          ) : null}
        </g>
      ))}
      {lv.high_24h !== null && lv.high_24h <= hi ? (
        <line x1={L} x2={R} y1={y(lv.high_24h)} y2={y(lv.high_24h)} stroke="#98989d" strokeDasharray="3 3" />
      ) : null}
      {lv.day_open !== null && lv.day_open >= lo && lv.day_open <= hi ? (
        <line x1={dayOpenX} x2={R} y1={y(lv.day_open)} y2={y(lv.day_open)} stroke="#0a84ff" strokeDasharray="4 3" />
      ) : null}
      {candles.map((c) => {
        const green = c.c >= c.o;
        const col = green ? '#30d158' : '#ff453a';
        const cx = x(c.t + step / 2);
        return (
          <g key={c.t}>
            <line x1={cx} x2={cx} y1={y(c.h)} y2={y(c.l)} stroke={col} strokeWidth={1} />
            <rect x={cx - cw / 2} y={y(Math.max(c.o, c.c))} width={cw} height={Math.max(1, Math.abs(y(c.o) - y(c.c)))} fill={col} />
            {c.v === null ? null : (
              <rect x={cx - cw / 2} y={VB - (c.v / vMax) * (VB - VT)} width={cw} height={(c.v / vMax) * (VB - VT)} fill={col} fillOpacity={0.35} />
            )}
            <rect x={cx - ((R - L) / candles.length) / 2} y={T} width={(R - L) / candles.length} height={VB - T} fill="transparent"
              {...tip(() => ({
                title: `${data.symbol} · ${timeEt(c.t)}${data.tf === '1d' || data.tf === '4h' ? ` ${dateEt(c.t)}` : ''} ET`,
                tone: green ? 'up' : 'down',
                what: `One ${data.tf} candle: where the price opened, how high and low it went, and where it closed. ${green ? 'Green: it closed higher than it opened.' : 'Red: it closed lower than it opened.'}`,
                visual: { kind: 'formula', parts: [
                  { label: 'open', value: price(c.o) }, { label: 'high', value: price(c.h), tone: 'up' },
                  { label: 'low', value: price(c.l), tone: 'down' }, { label: 'close', value: price(c.c), tone: green ? 'up' : 'down' },
                ], ops: ['·', '·', '·'] },
                now: c.v === null ? 'Volume: unknown (Coinbase gave none for this candle).' : `Volume: ${c.v.toLocaleString('en-US', { maximumFractionDigits: 2 })} ${data.symbol} on Coinbase.`,
              }))} />
          </g>
        );
      })}
      <line x1={L} x2={R} y1={y(last.c)} y2={y(last.c)} stroke={up ? '#30d158' : '#ff453a'} strokeOpacity={0.5} strokeDasharray="1 2" />
      {sc ? (
        // Drawn over the candles' hover strips, so the marker and its label answer for the stock close.
        <g {...tip(() => tipStockClose(data))}>
          <line x1={x(sc.at)} x2={x(sc.at)} y1={T - 12} y2={VB} stroke="#ff9f0a" strokeDasharray="3 3" />
          <line x1={x(sc.at)} x2={x(sc.at)} y1={T - 12} y2={VB} stroke="transparent" strokeWidth={9} />
          <rect x={x(sc.at) + 2} y={B - 30} width={96} height={26} fill="transparent" />
          <text x={x(sc.at) + 4} y={B - 18} className="cx-chart__lvl cx-chart__lvl--amber">Stock close {level(sc.price)}</text>
          {since ? <text x={x(sc.at) + 4} y={B - 7} className="cx-chart__lvl cx-chart__lvl--amber">{data.symbol} since {since}</text> : null}
        </g>
      ) : null}
      {tags.map((t) => (
        <g key={t.key} {...tip(() => tipChartLevel(t.key as 'high' | 'last' | 'open', data, timeEt(lv.day_open_at)))}>
          <rect x={R + 2} y={t.y - 8} width={W - R - 2} height={16} rx={3} fill={t.fill} />
          <text x={R + 6} y={t.y + 4} className="cx-chart__tag" fill={t.ink}>{t.text}</text>
        </g>
      ))}
      {data.sessions.map((s) => (
        <rect key={`strip-${s.kind}-${s.start}`} x={x(s.start)} y={VB + 6} width={Math.max(0, x(s.end) - x(s.start))} height={4}
          fill={s.kind === 'regular' ? '#30d158' : '#ff9f0a'} fillOpacity={s.kind === 'regular' ? 0.7 : 0.55} />
      ))}
      {timeLabels(candles, data.tf).map((l) => (
        <text key={l.t} x={x(l.t)} y={H - 4} className="cx-chart__axis" textAnchor="middle">{l.text}</text>
      ))}
    </svg>
  );
}
