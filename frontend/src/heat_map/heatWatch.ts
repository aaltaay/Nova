/**
 * How each wall left the book, and hidden size, for the heat map (ADR 061 amendment, operator ask 2026-10-21: "how do
 * I know if that bubble was completely [eaten] ... or did someone remove the wall?"). The depth socket's `book_watch`
 * frames carry the book watcher's own verdicts (ADR 033) -- the ones the Level 2 ladder shows for six seconds -- and
 * the heat map keeps them per stock for its 30 minutes, beside the books (`heatStore.ts`). Nothing is inferred here: a
 * drop is traded or pulled only as the watcher judged it, and a stock whose watcher is off keeps the reason it gave.
 *
 * Times are market time already: the watcher stamps a drop with Nova's receipt of the book live (the clock the tape's
 * prints carry) and with the recording's own time on a Sim replay (`source: "replay"`), the replay prints' clock.
 */
import { L2_BOOK_WATCH_SCHEMA_VERSION } from '../constants';
import { HEAT_REWIND_SEC, HEAT_WATCH_MAX_DROPS } from './heatMapConstants';
import { heatOf, heatStockFor, resetHeat } from './heatStore';

/** One large drop the watcher judged: the size that left a price, traded or pulled, at market time t. */
export interface HeatDrop {
  /** Its identity across frames: a socket's first frame repeats the last minute's drops. */
  key: string;
  t: number;
  side: 'bid' | 'ask';
  price: number;
  pulled: number;
  filled: number;
  /** The watcher's verdict: traded when more of it traded than was pulled. */
  traded: boolean;
  /** What stood at the price before the drop (null when the watcher did not say). */
  levelBefore: number | null;
  onApproach: boolean;
}

/** A hidden seller (the ask) or buyer (the bid): the watcher's newest word on one stretch, t0..t1 in market time. */
export interface HeatHidden {
  id: string;
  side: 'bid' | 'ask';
  price: number;
  t0: number;
  t1: number;
  /** What traded there beyond the most the book ever showed there. */
  hidden: number;
  printed: number;
  shownMax: number;
  state: string;
  /** When the watcher said this: a newer word replaces an older one. */
  said: number;
}

/** Whether the watcher follows the stock's line, and why not (its own words). */
export interface HeatWatchState {
  watching: boolean;
  reason: string | null;
}

const watchStates = new Map<string, HeatWatchState>();
const WATCH_STATES_KEEP = 16;

function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

function sideOf(v: unknown): 'bid' | 'ask' | null {
  return v === 'bid' || v === 'ask' ? v : null;
}

function readDrop(raw: unknown): HeatDrop | null {
  if (!raw || typeof raw !== 'object') return null;
  const d = raw as Record<string, unknown>;
  const t = num(d.ts);
  const price = num(d.price);
  const pulled = num(d.pulled);
  const filled = num(d.filled);
  const side = sideOf(d.side);
  if (t == null || price == null || pulled == null || filled == null || side == null) return null;
  return {
    key: `${t.toFixed(3)}|${side}|${price}`,
    t,
    side,
    price,
    pulled,
    filled,
    traded: d.outcome === 'traded',
    levelBefore: num(d.level_before),
    onApproach: d.on_approach === true,
  };
}

function readHidden(raw: unknown): HeatHidden | null {
  if (!raw || typeof raw !== 'object') return null;
  const h = raw as Record<string, unknown>;
  const said = num(h.ts);
  const price = num(h.price);
  const hidden = num(h.hidden);
  const side = sideOf(h.side);
  if (typeof h.id !== 'string' || said == null || price == null || hidden == null || side == null) return null;
  const t0 = num(h.started_ts) ?? said;
  return {
    id: h.id,
    side,
    price,
    t0,
    t1: Math.max(t0, num(h.ended_ts) ?? num(h.last_print_ts) ?? said),
    hidden,
    printed: num(h.printed) ?? hidden,
    shownMax: num(h.shown_max) ?? 0,
    state: typeof h.state === 'string' ? h.state : 'holding',
    said,
  };
}

function noteState(symbol: string, state: HeatWatchState): void {
  watchStates.delete(symbol);
  watchStates.set(symbol, state);
  if (watchStates.size > WATCH_STATES_KEEP) watchStates.delete(watchStates.keys().next().value as string);
}

/**
 * Fold one `book_watch` frame into the stock's verdicts: new drops in time order (a repeat is dropped by its key),
 * each hidden stretch's newest word. A replay frame that starts over far behind what the heat map holds means the
 * replay went back: the stock starts over, as on a print far behind the newest. An unknown schema is ignored.
 */
export function noteHeatWatch(symbol: string, raw: unknown): void {
  if (!raw || typeof raw !== 'object') return;
  const f = raw as Record<string, unknown>;
  if (f.schema_version !== L2_BOOK_WATCH_SCHEMA_VERSION) return;
  const reason = typeof f.reason === 'string' && f.reason.trim() ? f.reason : null;
  noteState(symbol, { watching: f.watching === true, reason });
  const drops = (Array.isArray(f.drops) ? f.drops : []).map(readDrop).filter((d): d is HeatDrop => d !== null);
  const words = (Array.isArray(f.hidden) ? f.hidden : []).map(readHidden).filter((h): h is HeatHidden => h !== null);
  const now = num(f.now);
  const held = heatOf(symbol);
  if (held && f.source === 'replay' && f.reset === true && now != null && now < held.lastPrintT - HEAT_REWIND_SEC) {
    resetHeat(symbol);
  }
  if (!drops.length && !words.length) {
    const s = heatOf(symbol);
    if (s) s.version += 1;   // the legend may have to say the watcher stopped
    return;
  }
  const s = heatStockFor(symbol, drops[0]?.price ?? words[0]?.price ?? null);
  if (!s) return;
  let unordered = false;
  for (const d of drops) {
    if (s.dropKeys.has(d.key)) continue;
    const last = s.drops[s.drops.length - 1];
    if (last && d.t < last.t) unordered = true;
    s.drops.push(d);
    s.dropKeys.add(d.key);
  }
  if (unordered) s.drops.sort((a, b) => a.t - b.t);
  if (s.drops.length > HEAT_WATCH_MAX_DROPS) {
    for (const d of s.drops.splice(0, s.drops.length - HEAT_WATCH_MAX_DROPS)) s.dropKeys.delete(d.key);
  }
  for (const h of words) {
    const had = s.hidden.get(h.id);
    if (!had || had.said <= h.said) s.hidden.set(h.id, h);
  }
  s.version += 1;
}

/** Whether the watcher follows this stock's line (null before its first frame). */
export function heatWatchState(symbol: string): HeatWatchState | null {
  return watchStates.get(symbol) ?? null;
}

/** Tests only: forget every watcher state. */
export function resetHeatWatchForTests(): void {
  watchStates.clear();
}
