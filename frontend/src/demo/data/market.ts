/**
 * Nova Marketing Sample Data for the demo (ADR 043): one coherent, deterministic morning.
 * No live market, no real account.
 *
 * The story: Wednesday 2026-09-30, 09:41:27 ET. SMPL (Sample Pharma) gapped on a sample FDA
 * fast-track headline at 07:00, built a premarket range, broke it at the 09:30 open, pulled back,
 * and is now pressing the high of day.
 */

export const DAY = '2026-09-30';
/** Eastern daylight time: UTC-4. */
const ET_OFFSET_H = 4;

/** Epoch ms for an ET wall time on `day`. */
export function etMs(h: number, m = 0, s = 0, day = DAY): number {
  const [Y, M, D] = day.split('-').map(Number);
  return Date.UTC(Y, M - 1, D, h + ET_OFFSET_H, m, s);
}

/** The sample morning's "now": where the demo clock starts. */
export const NOW_MS = etMs(9, 41, 27);
export const NOW_S = NOW_MS / 1000;
export const SMPL_DAY_VOLUME = 31_240_000;
export const iso = (ms: number): string => new Date(ms).toISOString();

/** A candle on the sample day. `minute` is the ET minute of day (intraday bars only). */
export interface Bar {
  minute?: number;
  t: number;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
}

export interface BookRow {
  price: number;
  size: number;
  mm: string;
  row: number;
}

export interface SamplePrint {
  ms: number;
  price: number;
  size: number;
  side: 'ask' | 'bid';
  bid: number;
  ask: number;
}

/** Deterministic randomness (mulberry32), so every visitor sees the same morning. */
export function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export const r2 = (x: number): number => Math.round(x * 100) / 100;
const r4 = (x: number): number => Math.round(x * 10000) / 10000;

// [ET minute of day, price] anchors; the minute bars wander between them.
const SMPL_PATH: ReadonlyArray<readonly [number, number]> = [
  [240, 2.86], [280, 2.9], [330, 2.88], [375, 2.93], [419, 2.95],
  // 07:00 the headline
  [421, 3.21], [423, 3.56], [425, 3.41], [428, 3.79], [432, 3.58],
  [440, 3.66], [455, 3.6], [470, 3.74], [485, 3.63], [500, 3.71],
  [514, 3.86], [525, 3.77], [540, 3.94], [550, 3.88], [558, 4.09],
  [566, 4.01], [569, 4.06],
  // the open
  [570, 4.18], [571, 4.29], [572, 4.37], [573, 4.31], [574, 4.24],
  [575, 4.19], [576, 4.16], [577, 4.21], [578, 4.25], [579, 4.29],
  [580, 4.31], [581, 4.33],
];

/** Volume shape per ET minute (shares). */
function smplVolume(t: number, rand: () => number): number {
  let base = 6_000;
  if (t >= 420 && t < 432) base = 420_000 - (t - 420) * 26_000;
  else if (t >= 432 && t < 480) base = 70_000;
  else if (t >= 480 && t < 540) base = 55_000;
  else if (t >= 540 && t < 570) base = 95_000;
  else if (t >= 570 && t < 574) base = 620_000 - (t - 570) * 60_000;
  else if (t >= 574) base = 260_000;
  return Math.round(base * (0.65 + rand() * 0.7));
}

function interp(minute: number): number {
  for (let i = 1; i < SMPL_PATH.length; i += 1) {
    const [m1, p1] = SMPL_PATH[i];
    const [m0, p0] = SMPL_PATH[i - 1];
    if (minute <= m1) return p0 + (p1 - p0) * ((minute - m0) / Math.max(1, m1 - m0));
  }
  return SMPL_PATH[SMPL_PATH.length - 1][1];
}

/** SMPL's one-minute bars from 04:00 ET to the 09:41 minute (the last one forming). */
export function smplMinuteBars(): Bar[] {
  const rand = rng(20260930);
  const bars: Bar[] = [];
  const end = 581;
  let prevClose = 2.86;
  for (let minute = 240; minute <= end; minute += 1) {
    const target = interp(minute);
    const noise = (rand() - 0.5) * (minute >= 570 ? 0.05 : minute >= 420 ? 0.04 : 0.012);
    const open = minute === 240 ? 2.86 : prevClose;
    let close = r2(target + noise * 0.6);
    if (minute === end) close = 4.33;
    const span = Math.abs(close - open);
    const wick = (minute >= 420 ? 0.035 : 0.01) * (0.4 + rand());
    let high = r2(Math.max(open, close) + wick * rand() + span * 0.15 * rand());
    let low = r2(Math.min(open, close) - wick * rand() - span * 0.15 * rand());
    // Keep the story's highs: 4.38 is the high of day (09:32), 4.12 the premarket high (09:18).
    if (minute === 572) high = 4.38;
    if (minute === 558) high = 4.12;
    if (minute === 428) high = 3.84;
    if (minute === 576) low = 4.13;
    if (minute !== 572 && high >= 4.38) high = 4.37;
    if (minute < 570 && minute !== 558 && high >= 4.12) high = 4.11;
    if (minute === end) {
      high = Math.max(high, 4.34);
      low = Math.min(low, 4.3);
    }
    bars.push({ minute, t: etMs(Math.floor(minute / 60), minute % 60), o: r2(open), h: high, l: low, c: close, v: smplVolume(minute, rand) });
    prevClose = close;
  }
  // The day's volume matches the scanner row.
  const total = bars.reduce((a, b) => a + b.v, 0);
  const k = SMPL_DAY_VOLUME / total;
  for (const b of bars) b.v = Math.max(100, Math.round((b.v * k) / 100) * 100);
  return bars;
}

/** Aggregate one-minute bars into N-minute candles on the clock. */
export function aggregate(bars: Bar[], n: number): Bar[] {
  const out: Bar[] = [];
  for (const b of bars) {
    const bucket = Math.floor((b.minute ?? 0) / n) * n;
    const last = out[out.length - 1];
    if (last && last.minute === bucket) {
      last.h = Math.max(last.h, b.h);
      last.l = Math.min(last.l, b.l);
      last.c = b.c;
      last.v += b.v;
    } else {
      out.push({ minute: bucket, t: etMs(Math.floor(bucket / 60), bucket % 60), o: b.o, h: b.h, l: b.l, c: b.c, v: b.v });
    }
  }
  return out;
}

/** Ten-second bars for the last `minutes` minutes, six per minute, honouring each minute's OHLC. */
export function tenSecondBars(minuteBars: Bar[], minutes = 42): Bar[] {
  const rand = rng(7);
  const out: Bar[] = [];
  for (const b of minuteBars.slice(-minutes)) {
    const pts = [b.o];
    const upFirst = b.c >= b.o ? rand() < 0.35 : rand() < 0.7;
    const a = upFirst ? b.h : b.l;
    const z = upFirst ? b.l : b.h;
    for (let i = 1; i < 6; i += 1) {
      let p = b.o + (b.c - b.o) * (i / 6) + (rand() - 0.5) * (b.h - b.l) * 0.5;
      if (i === 2) p = a;
      if (i === 4) p = z;
      pts.push(Math.min(b.h, Math.max(b.l, p)));
    }
    pts.push(b.c);
    for (let i = 0; i < 6; i += 1) {
      const o = r2(pts[i]);
      const c = r2(pts[i + 1]);
      const h = r2(Math.min(b.h, Math.max(o, c) + rand() * 0.01));
      const l = r2(Math.max(b.l, Math.min(o, c) - rand() * 0.01));
      out.push({ t: b.t + i * 10_000, o, h, l, c, v: Math.round((b.v / 6) * (0.6 + rand() * 0.8)) });
    }
  }
  return out;
}

/** A year of SMPL daily bars: a slow bleed from ~$9 with three +40% runs, then today's gap. */
export function smplDailyBars(today: Omit<Bar, 't'>): Bar[] {
  const rand = rng(99);
  const out: Bar[] = [];
  const start = Date.UTC(2025, 8, 29);
  const runs = new Set([62, 141, 203]);
  let px = 9.4;
  let d = 0;
  for (let day = 0; day < 366; day += 1) {
    const ms = start + day * 86_400_000;
    const date = new Date(ms);
    const wd = date.getUTCDay();
    if (wd === 0 || wd === 6) continue;
    if (ms >= Date.UTC(2026, 8, 30)) break;
    d += 1;
    const drift = -0.0042 + (rand() - 0.5) * 0.045;
    let o = px * (1 + (rand() - 0.5) * 0.02);
    let c = px * (1 + drift);
    let h = Math.max(o, c) * (1 + rand() * 0.035);
    const l = Math.min(o, c) * (1 - rand() * 0.035);
    let v = Math.round(250_000 + rand() * 900_000);
    if (runs.has(d)) {
      h = px * (1.48 + rand() * 0.2);
      c = px * (1.18 + rand() * 0.1);
      o = px * 1.08;
      v = Math.round(9_000_000 + rand() * 14_000_000);
    }
    out.push({ t: Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate(), 4), o: r2(o), h: r2(h), l: r2(l), c: r2(c), v });
    px = Math.max(1.2, c);
  }
  // Bend the path in log space so it settles at the story's 2.80 prior close.
  const want = Math.log(2.8 / out[out.length - 1].c);
  out.forEach((b, i) => {
    const f = Math.exp((want * i) / (out.length - 1));
    b.o = r2(b.o * f);
    b.h = r2(b.h * f);
    b.l = r2(b.l * f);
    b.c = r2(b.c * f);
  });
  out[out.length - 1].c = 2.8;
  out.push({ t: Date.UTC(2026, 8, 30, 4), ...today });
  return out;
}

export function vwapOf(bars: Bar[]): number | null {
  let pv = 0;
  let vv = 0;
  for (const b of bars) {
    pv += ((b.h + b.l + b.c) / 3) * b.v;
    vv += b.v;
  }
  return vv ? r4(pv / vv) : null;
}

/** Wire candles: `{t: ISO, o, h, l, c, v}`. */
export const wireBars = (bars: Bar[]) => bars.map((b) => ({ t: iso(b.t), o: b.o, h: b.h, l: b.l, c: b.c, v: b.v }));

const VENUES = ['NSDQ', 'ARCA', 'EDGX', 'BATS', 'MEMX', 'IEX', 'NYSE', 'EDGA', 'BYX', 'PEARL', 'LTSE', 'AMEX'];

/** A Level 2 book around `last`; for SMPL, stacked bids at 4.30 and a seller at 4.40. */
export function sampleBook(last: number, seed = 3): { bids: BookRow[]; asks: BookRow[] } {
  const rand = rng(seed);
  const lot = (lo: number, hi: number) => Math.round(lo + rand() * (hi - lo)) * 100;
  const bids: BookRow[] = [];
  const asks: BookRow[] = [];
  const bestBid = r2(last - 0.01);
  const bestAsk = r2(last);
  for (let i = 0; i < 16; i += 1) {
    const price = r2(bestBid - Math.floor(i / 1.7) * 0.01);
    const size = Math.abs(price - 4.3) < 0.001 && i % 2 === 0 ? 14_500 : lot(2, 28);
    bids.push({ price, size, mm: VENUES[(i * 5 + 1) % VENUES.length], row: i });
  }
  for (let i = 0; i < 16; i += 1) {
    const price = r2(bestAsk + Math.floor(i / 1.7) * 0.01);
    const size = Math.abs(price - 4.4) < 0.001 && i % 2 === 0 ? 21_000 : lot(1, 22);
    asks.push({ price, size, mm: VENUES[(i * 7 + 3) % VENUES.length], row: i });
  }
  return { bids, asks };
}

/** Prints, oldest first, ending at `endMs`: buyers lifting the offer at `last`. */
export function sampleTape(count: number, endMs: number, last: number): SamplePrint[] {
  const rand = rng(11);
  const prints: SamplePrint[] = [];
  let ms = endMs - count * 640;
  let bid = r2(last - 0.02);
  for (let i = 0; i < count; i += 1) {
    ms += 220 + Math.floor(rand() * 820);
    if (i === Math.floor(count * 0.55)) bid = r2(last - 0.01);
    const ask = r2(bid + 0.01);
    const lift = rand() < 0.68;
    const odd = rand() < 0.12;
    const size = odd
      ? [17, 25, 40, 50, 75][Math.floor(rand() * 5)]
      : rand() < 0.08 ? Math.round(20 + rand() * 50) * 100 : Math.round(1 + rand() * 14) * 100;
    prints.push({ ms: Math.min(ms, endMs - (count - i) * 5), price: lift ? ask : bid, size, side: lift ? 'ask' : 'bid', bid, ask });
  }
  Object.assign(prints[prints.length - 1], { price: last, size: 500, side: 'ask', bid: r2(last - 0.01), ask: last, ms: endMs - 400 });
  return prints;
}
