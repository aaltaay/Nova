/**
 * What the heat map draws from (ADR 061): each stock's recent Level 2 books, bursts of trades and volume per second,
 * fed by the Trader's own depth and tape sockets (`ibkr/useIbkrDepth`, `ibkr/useIbkrTape`) -- no socket or IBKR line
 * of its own. Memory only: it starts when Nova opens the stock's Level 2 (IBKR keeps no book history) and keeps
 * HEAT_KEEP_SEC. Nothing here is inferred: a price outside the rows IBKR sent is "not seen", never an empty level.
 *
 * Time is market time: a print carries its own (the replay's on a Sim desk, Nova's receipt live); a book is stamped
 * with the browser clock plus the newest print's offset from it, so books and prints share one clock on every venue.
 * A print far behind the newest means the replay went back: the stock starts over (as on a `scrub_reset`).
 */
import {
  HEAT_ALIVE_GRACE_SEC,
  HEAT_BOOK_SLOT_SEC,
  HEAT_BURST_GAP_SEC,
  HEAT_BURST_MOVE_TICKS,
  HEAT_KEEP_SEC,
  HEAT_MAX_HALF_TICKS,
  HEAT_MAX_SYMBOLS,
  HEAT_REPLAY_OFFSET_SEC,
  HEAT_REWIND_SEC,
  HEAT_TICK_DOLLAR,
  HEAT_TICK_SUB_DOLLAR,
} from './heatMapConstants';
import type { HeatDrop, HeatHidden } from './heatWatch';

/** One level as the depth socket sends it (only what the heat map reads). */
export interface HeatLevelIn {
  price: number;
  size: number;
}

/** One book: tick indices `lo`..`lo + sizes.length - 1` were inside the rows IBKR sent; sizes are summed per tick. */
export interface HeatSnap {
  t: number;
  lo: number;
  sizes: Float32Array;
  /** Best bid / ask tick (NaN when that side is empty). */
  bb: number;
  ba: number;
}

/** Side codes: 0 bought at the ask, 1 sold at the bid, 2 between or unknown. */
export type HeatSide = 0 | 1 | 2;

/** A burst of trades: one dot. `pv` is price x shares, so `pv / sz` is its average price. */
export interface HeatBurst {
  t0: number;
  t1: number;
  sz: number;
  pv: number;
  side: HeatSide;
  /** The tick of its first print (the move limit is measured from it). */
  c0: number;
}

export interface HeatLine {
  state: 'lent' | 'error';
  why: string;
}

export interface HeatSymbol {
  /** Dollars per row: a cent, or a tenth of a cent under $1 (fixed at the first book). */
  tick: number;
  snaps: HeatSnap[];
  bursts: HeatBurst[];
  /** The burst still growing on the aggressor stream (ask / bid) and on the in-between stream. */
  open: [HeatBurst | null, HeatBurst | null];
  /** Volume per whole market second, a ring: the second each slot holds, and its ask / bid / between shares. */
  volSec: Float64Array;
  vol: Float64Array;
  lastPrintT: number;
  lastPrice: number | null;
  /** Market time minus the browser clock, from the newest print (0 until one arrives). */
  offset: number;
  lastBookT: number;
  /** The newest moment the line was known alive (a book or a beat). */
  aliveT: number;
  /** Browser clock (ms) of the newest depth frame, book or beat: a silent socket shows here on any venue. */
  depthWallMs: number;
  l1: boolean;
  line: HeatLine | null;
  /** The book watcher's verdicts (`heatWatch.ts`): large drops oldest first, their keys, hidden stretches by id. */
  drops: HeatDrop[];
  dropKeys: Set<string>;
  hidden: Map<string, HeatHidden>;
  /** Bumped on every change: the view redraws only when it moves (or the clock does). */
  version: number;
  fedAt: number;
}

const VOL_SLOTS = HEAT_KEEP_SEC + 120;
const stocks = new Map<string, HeatSymbol>();
/** A refused or lent line before the stock's first book or print: kept so the view can say why (bounded). */
const pendingLines = new Map<string, HeatLine>();
const PENDING_LINES_KEEP = 16;


function blank(tick: number): HeatSymbol {
  return {
    tick,
    snaps: [],
    bursts: [],
    open: [null, null],
    volSec: new Float64Array(VOL_SLOTS).fill(-1),
    vol: new Float64Array(VOL_SLOTS * 3),
    lastPrintT: Number.NEGATIVE_INFINITY,
    lastPrice: null,
    offset: 0,
    lastBookT: Number.NEGATIVE_INFINITY,
    aliveT: Number.NEGATIVE_INFINITY,
    depthWallMs: Number.NEGATIVE_INFINITY,
    l1: false,
    line: null,
    drops: [],
    dropKeys: new Set(),
    hidden: new Map(),
    version: 0,
    fedAt: 0,
  };
}

function tickFor(price: number): number {
  return price >= 1 ? HEAT_TICK_DOLLAR : HEAT_TICK_SUB_DOLLAR;
}

/** The stock's heat, made on first use; the least recently fed is dropped past HEAT_MAX_SYMBOLS. */
function stock(symbol: string, price: number | null): HeatSymbol | null {
  let s = stocks.get(symbol);
  if (s) return s;
  if (price == null || !Number.isFinite(price) || price <= 0) return null;
  s = blank(tickFor(price));
  stocks.set(symbol, s);
  if (stocks.size > HEAT_MAX_SYMBOLS) {
    let oldest: string | null = null;
    for (const [sym, v] of stocks) if (sym !== symbol && (oldest == null || v.fedAt < stocks.get(oldest)!.fedAt)) oldest = sym;
    if (oldest) stocks.delete(oldest);
  }
  return s;
}

const nowSec = (wallMs: number) => wallMs / 1000;

/** Drop everything older than the keep window (cheap: at most once a second of new data). */
function trim(s: HeatSymbol, t: number): void {
  const cut = t - HEAT_KEEP_SEC;
  if (s.snaps.length > 1 && s.snaps[1].t < cut) {
    let k = 0;
    while (k + 1 < s.snaps.length && s.snaps[k + 1].t < cut) k += 1;   // keep the book in force at the cut
    s.snaps.splice(0, k);
  }
  if (s.bursts.length && s.bursts[0].t1 < cut) {
    let k = 0;
    while (k < s.bursts.length && s.bursts[k].t1 < cut) k += 1;
    s.bursts.splice(0, k);
  }
  if (s.drops.length && s.drops[0].t < cut) {
    let k = 0;
    while (k < s.drops.length && s.drops[k].t < cut) k += 1;
    for (const d of s.drops.splice(0, k)) s.dropKeys.delete(d.key);
  }
  for (const [id, h] of s.hidden) if (h.t1 < cut) s.hidden.delete(id);
}

/** The stock's heat, made on first use from a price (the book watcher's verdicts can arrive before its first book). */
export function heatStockFor(symbol: string, price: number | null): HeatSymbol | null {
  return stock(symbol, price);
}

/** A Level 2 book from the depth socket. `wallMs` is the browser clock at receipt. */
export function noteHeatBook(
  symbol: string, bids: readonly HeatLevelIn[], asks: readonly HeatLevelIn[], l1Fallback: boolean, wallMs = Date.now(),
): void {
  const first = bids[0]?.price ?? asks[0]?.price ?? null;
  const s = stock(symbol, first);
  if (!s) return;
  const t = nowSec(wallMs) + s.offset;
  const rows = new Map<number, number>();
  const bidTicks: number[] = [];
  const askTicks: number[] = [];
  const add = (lv: HeatLevelIn, bid: boolean) => {
    if (!Number.isFinite(lv.price) || !Number.isFinite(lv.size) || lv.size < 0) return;
    const k = Math.round(lv.price / s.tick);
    rows.set(k, (rows.get(k) ?? 0) + lv.size);
    (bid ? bidTicks : askTicks).push(k);
  };
  for (const lv of bids) add(lv, true);
  for (const lv of asks) add(lv, false);
  s.l1 = l1Fallback;
  s.line = null;
  pendingLines.delete(symbol);
  s.aliveT = Math.max(s.aliveT, t);
  s.depthWallMs = wallMs;
  s.fedAt = wallMs;
  if (!rows.size) {
    s.version += 1;
    return;
  }
  let lo = Math.min(...rows.keys());
  let hi = Math.max(...rows.keys());
  if (hi - lo > 2 * HEAT_MAX_HALF_TICKS) {
    // Centre on where the stock trades (its last print, else its last middle): a far-off row is cut even when the
    // book has only two rows. With neither yet, the lower middle row.
    const keys = [...rows.keys()].sort((a, b) => a - b);
    const prev = s.snaps[s.snaps.length - 1];
    const prevMid = prev && Number.isFinite(prev.bb) && Number.isFinite(prev.ba) ? (prev.bb + prev.ba) / 2 : Number.NaN;
    const ref = s.lastPrice != null ? s.lastPrice / s.tick : prevMid;
    const near = Number.isFinite(ref) ? keys.filter((k) => Math.abs(k - ref) <= HEAT_MAX_HALF_TICKS) : [];
    const mid = near.length ? Math.round(ref) : keys[Math.floor((keys.length - 1) / 2)];
    lo = Math.max(lo, mid - HEAT_MAX_HALF_TICKS);
    hi = Math.min(hi, mid + HEAT_MAX_HALF_TICKS);
  }
  // The best bid / ask from the rows kept, so a cut-off outlier can never stretch the screen's range.
  const kept = (ticks: number[]) => ticks.filter((k) => k >= lo && k <= hi);
  const bbs = kept(bidTicks);
  const bas = kept(askTicks);
  const bb = bbs.length ? Math.max(...bbs) : Number.NaN;
  const ba = bas.length ? Math.min(...bas) : Number.NaN;
  const sizes = new Float32Array(hi - lo + 1);
  for (const [k, v] of rows) if (k >= lo && k <= hi) sizes[k - lo] = v;
  const snap: HeatSnap = { t, lo, sizes, bb, ba };
  const last = s.snaps[s.snaps.length - 1];
  if (last && Math.floor(last.t / HEAT_BOOK_SLOT_SEC) === Math.floor(t / HEAT_BOOK_SLOT_SEC)) {
    s.snaps[s.snaps.length - 1] = { ...snap, t: last.t };   // the newest book in the slot wins
  } else {
    s.snaps.push(snap);
  }
  s.lastBookT = t;
  trim(s, t);
  s.version += 1;
}

/**
 * On a replay's clock (the prints' time far from the browser's) market time moves only with the replay: a beat is
 * the browser clock and keeps coming while the replay is paused, so there it never stretches the last book.
 */
export function onReplayClock(s: HeatSymbol): boolean {
  return Math.abs(s.offset) > HEAT_REPLAY_OFFSET_SEC;
}

/** The depth line is alive with no new book (the socket's `beat`, stamped with the browser clock). */
export function noteHeatBeat(symbol: string, wallMs = Date.now()): void {
  const s = stocks.get(symbol);
  if (!s) return;
  s.depthWallMs = wallMs;   // the socket is alive, on any venue
  if (onReplayClock(s)) return;
  s.aliveT = Math.max(s.aliveT, nowSec(wallMs) + s.offset);
  s.version += 1;
}

/** The depth line was lent to a setup or refused: the view says so, with or without a book yet. */
export function noteHeatLine(symbol: string, state: HeatLine['state'], why: string): void {
  const s = stocks.get(symbol);
  if (s) {
    s.line = { state, why };
    s.version += 1;
    return;
  }
  pendingLines.delete(symbol);
  pendingLines.set(symbol, { state, why });
  if (pendingLines.size > PENDING_LINES_KEEP) pendingLines.delete(pendingLines.keys().next().value as string);
}

/** Why a stock with no heat yet has no line (refused or lent), or null. */
export function heatPendingLine(symbol: string): HeatLine | null {
  return pendingLines.get(symbol) ?? null;
}

function sideOf(side: string | null | undefined): HeatSide {
  return side === 'ask' ? 0 : side === 'bid' ? 1 : 2;
}

function closeBurst(s: HeatSymbol, stream: 0 | 1): void {
  const b = s.open[stream];
  if (b) s.bursts.push(b);
  s.open[stream] = null;
}

/** One print from the tape socket: its own time (ISO), price, shares and the desk's side verdict. */
export function noteHeatPrint(
  symbol: string, time: string, price: number, size: number, side: string | null | undefined, wallMs = Date.now(),
): void {
  if (!Number.isFinite(price) || !Number.isFinite(size) || size <= 0) return;
  const s = stock(symbol, price);
  if (!s) return;
  const parsed = Date.parse(time) / 1000;
  const t = Number.isFinite(parsed) ? parsed : nowSec(wallMs) + s.offset;
  if (t < s.lastPrintT - HEAT_REWIND_SEC) {
    resetHeat(symbol);
    noteHeatPrint(symbol, time, price, size, side, wallMs);
    return;
  }
  const offset = t - nowSec(wallMs);
  const shift = offset - s.offset;
  if (s.snaps.length && Math.abs(shift) > HEAT_REWIND_SEC) {
    // The clock moved under the books stamped since the last print: the first print names a replay's clock, a
    // replay held on pause (or moved ahead) leaves them off by the pause. Put them back on the print's clock, in order.
    // A book that would land before the last print was stamped right (before the pause) and stays.
    const since = Number.isFinite(s.lastPrintT) ? s.lastPrintT : Number.NEGATIVE_INFINITY;
    let floor = since;
    for (const sn of s.snaps) {
      if (sn.t <= since) continue;
      const moved = sn.t + shift;
      if (moved >= since) sn.t = moved;
      sn.t = Math.max(sn.t, floor);   // keep them in order
      floor = sn.t;
    }
    const newest = s.snaps[s.snaps.length - 1].t;
    s.lastBookT = newest;
    s.aliveT = Math.max(newest, Number.isFinite(since) ? since : newest);
  }
  s.offset = offset;
  s.lastPrintT = Math.max(s.lastPrintT, t);
  // On a replay's clock a print is the replay moving on; the recorded book would have changed if it had.
  if (onReplayClock(s) && s.snaps.length) s.aliveT = Math.max(s.aliveT, t);
  s.lastPrice = price;
  s.fedAt = wallMs;
  const sd = sideOf(side);
  const c = Math.round(price / s.tick);
  const stream: 0 | 1 = sd === 2 ? 1 : 0;
  const cur = s.open[stream];
  const breaks = cur != null && (cur.side !== sd || t - cur.t1 > HEAT_BURST_GAP_SEC || Math.abs(c - cur.c0) > HEAT_BURST_MOVE_TICKS);
  if (cur && !breaks) {
    cur.t1 = Math.max(cur.t1, t);
    cur.sz += size;
    cur.pv += price * size;
  } else {
    closeBurst(s, stream);
    s.open[stream] = { t0: t, t1: t, sz: size, pv: price * size, side: sd, c0: c };
  }
  const sec = Math.floor(t);
  const slot = ((sec % VOL_SLOTS) + VOL_SLOTS) % VOL_SLOTS;
  if (s.volSec[slot] !== sec) {
    s.volSec[slot] = sec;
    s.vol[slot * 3] = 0;
    s.vol[slot * 3 + 1] = 0;
    s.vol[slot * 3 + 2] = 0;
  }
  s.vol[slot * 3 + sd] += size;
  trim(s, t);
  s.version += 1;
}

/** The replay was scrubbed (or went back): this stock's heat starts over. */
export function resetHeat(symbol: string): void {
  const s = stocks.get(symbol);
  if (!s) return;
  stocks.set(symbol, { ...blank(s.tick), version: s.version + 1, fedAt: s.fedAt, depthWallMs: s.depthWallMs });
}

/** The stock's heat, or null before its first book or print. The view reads it; only the feeds write. */
export function heatOf(symbol: string): HeatSymbol | null {
  return stocks.get(symbol) ?? null;
}

/** Shares on each side in market second `sec` (zeros when that second is not held). */
export function heatVolumeAt(s: HeatSymbol, sec: number): [number, number, number] {
  const slot = ((sec % VOL_SLOTS) + VOL_SLOTS) % VOL_SLOTS;
  if (s.volSec[slot] !== sec) return [0, 0, 0];
  return [s.vol[slot * 3], s.vol[slot * 3 + 1], s.vol[slot * 3 + 2]];
}

/** Every burst, the growing ones included (a growing burst is drawn where it stands now). */
export function heatBursts(s: HeatSymbol): HeatBurst[] {
  const open = s.open.filter((b): b is HeatBurst => b != null);
  return open.length ? [...s.bursts, ...open] : s.bursts;
}

/** When the book last counted as live, market time: the newest book or beat, plus a short grace. */
export function heatAliveUntil(s: HeatSymbol): number {
  return s.aliveT + HEAT_ALIVE_GRACE_SEC;
}

/** Tests only: forget every stock. */
export function resetAllHeatForTests(): void {
  stocks.clear();
  pendingLines.clear();
}
