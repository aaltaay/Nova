/**
 * What left the book, on the Level 2 ladder (ADR 033 amendment, 2026-09-29). Pure: the depth socket's
 * `book_watch` frames go in; each side's marks (a large level that traded or was pulled, where it was),
 * its "pulled here" tags and its line of the last minute come out. The backend's book watcher judges
 * every drop; nothing here infers a verdict. Hints consistent with spoofing -- never a detection.
 * The frames also carry the watcher's hidden sellers and buyers (2026-09-30), folded here and drawn by
 * bookWatchHidden.ts.
 */
import {
  L2_BOOK_WATCH_SCHEMA_VERSION,
  L2_HIDDEN_STALE_MS,
  L2_PULLED_HERE_MEMORY_SEC,
  L2_PULLS_IDLE_REASON,
  L2_PULLS_NOTE,
  L2_PULLS_WARN_MIN_SHARES,
  L2_PULLS_WARN_RATIO,
  L2_PULL_MARK_FADE_MS,
  L2_PULL_MARK_FULL_BELOW,
  L2_PULL_MARK_SHOW_MS,
} from '../constants';
import { fmtVolume } from '../utils/quoteFormat';
import { markerPlace } from './depthMarkers';
import type { DepthLevel } from './types';

export type BookSide = 'bid' | 'ask';

/** One large drop the watcher judged, with the local time it happened (`atMs`). */
export interface HeldDrop {
  seq: number;
  side: BookSide;
  price: number;
  pulled: number;
  filled: number;
  traded: boolean;
  levelBefore: number | null;
  levelAfter: number | null;
  distanceTicks: number | null;
  distanceAtPostTicks: number | null;
  lifetimeSec: number | null;
  largePull: boolean;
  onApproach: boolean;
  atMs: number;
}

/**
 * A hidden seller (the ask) or hidden buyer (the bid): the watcher's newest word on one stretch -- a price
 * that held while more traded there than the book ever showed there. `hidden` is what traded beyond that.
 */
export interface HeldHidden {
  id: string;
  seq: number;
  side: BookSide;
  price: number;
  /** `holding`, or how it ended: `broke` | `faded` | `moved` | `auction` | `reset`. */
  state: string;
  hidden: number;
  printed: number;
  shownMax: number;
  refills: number;
  heldSec: number;
  atMs: number;
}

export interface SideTotals {
  pulled: number;
  traded: number;
  largePulls: number;
  /** Hidden size at the side's flagged prices in the watcher's minute (0 from a backend without it). */
  hidden: number;
}

export interface BookWatchState {
  watching: boolean;
  reason: string | null;
  windowSec: number;
  sides: Record<BookSide, SideTotals> | null;
  drops: HeldDrop[];
  hidden: HeldHidden[];
}

export type PullMarkKind = 'pulled' | 'approach' | 'traded' | 'hidden';

/** A mark between the rows where the size was (placed like the plan's levels, depthMarkers.ts). */
export interface PullMark {
  id: string;
  kind: PullMarkKind;
  before: number;
  beyond: boolean;
  opacity: number;
  label: string;
  title: string;
  tip: string;
}

export interface PulledHere {
  count: number;
  title: string;
  tip: string;
}

export interface PullsLine {
  watching: boolean;
  pulled: string;
  traded: string;
  /** `◆ 2.4K` while the side has hidden size at a flagged price, else empty. */
  hidden: string;
  warn: boolean;
  title: string;
  tip: string;
}

const MEMORY_MS = L2_PULLED_HERE_MEMORY_SEC * 1000;
const SIDE_WORD: Record<BookSide, string> = { bid: 'bid', ask: 'offered' };
const SIDE_NAME: Record<BookSide, string> = { bid: 'Bids', ask: 'Asks' };

function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

const whole = (n: number) => Math.round(n).toLocaleString('en-US');
const shares = (n: number) => (n < L2_PULL_MARK_FULL_BELOW ? whole(n) : fmtVolume(n));
const px = (p: number) => p.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
const secs = (ms: number) => `${(Math.max(0, ms) / 1000).toFixed(1)} s`;
export const priceKey = (p: number) => p.toFixed(4);
/** The marks' own words for sizes and prices (bookWatchHidden.ts writes the same way). */
export { whole as markWhole, shares as markShares, px as markPrice };

function readDrop(raw: unknown, atOf: (ts: number) => number): HeldDrop | null {
  if (!raw || typeof raw !== 'object') return null;
  const d = raw as Record<string, unknown>;
  const seq = num(d.seq);
  const ts = num(d.ts);
  const price = num(d.price);
  const pulled = num(d.pulled);
  const filled = num(d.filled);
  if (seq == null || ts == null || price == null || pulled == null || filled == null) return null;
  if (d.side !== 'bid' && d.side !== 'ask') return null;
  return {
    seq,
    side: d.side,
    price,
    pulled,
    filled,
    traded: d.outcome === 'traded',
    levelBefore: num(d.level_before),
    levelAfter: num(d.level_after),
    distanceTicks: num(d.distance_ticks),
    distanceAtPostTicks: num(d.distance_at_post_ticks),
    lifetimeSec: num(d.lifetime_sec),
    largePull: d.large_pull === true,
    onApproach: d.on_approach === true,
    atMs: atOf(ts),
  };
}

function readHidden(raw: unknown, atOf: (ts: number) => number): HeldHidden | null {
  if (!raw || typeof raw !== 'object') return null;
  const h = raw as Record<string, unknown>;
  const seq = num(h.seq);
  const ts = num(h.ts);
  const price = num(h.price);
  const hidden = num(h.hidden);
  if (typeof h.id !== 'string' || seq == null || ts == null || price == null || hidden == null) return null;
  if ((h.side !== 'bid' && h.side !== 'ask') || typeof h.state !== 'string') return null;
  const started = num(h.started_ts);
  const last = num(h.last_print_ts);
  return {
    id: h.id,
    seq,
    side: h.side,
    price,
    state: h.state,
    hidden,
    printed: num(h.printed) ?? hidden,
    shownMax: num(h.shown_max) ?? 0,
    refills: num(h.refills) ?? 0,
    heldSec: started != null && last != null ? Math.max(0, last - started) : 0,
    atMs: atOf(ts),
  };
}

/** Is a hidden seller or buyer still worth keeping: holding and heard from lately, or ended within the minute. */
function hiddenAlive(h: HeldHidden, nowMs: number): boolean {
  const age = nowMs - h.atMs;
  return h.state === 'holding' ? age <= L2_HIDDEN_STALE_MS : age <= MEMORY_MS;
}

function readSides(raw: unknown): Record<BookSide, SideTotals> | null {
  if (!raw || typeof raw !== 'object') return null;
  const out = {} as Record<BookSide, SideTotals>;
  for (const side of ['bid', 'ask'] as const) {
    const s = (raw as Record<string, unknown>)[side] as Record<string, unknown> | undefined;
    const pulled = num(s?.pulled_shares);
    const traded = num(s?.filled_shares);
    if (pulled == null || traded == null) return null;
    out[side] = { pulled, traded, largePulls: num(s?.large_pulls) ?? 0, hidden: num(s?.hidden_shares) ?? 0 };
  }
  return out;
}

/**
 * Fold one `book_watch` frame into the ladder's state. A `reset` frame starts over; the others add the
 * drops judged since. Drop times are moved onto this page's clock through the frame's `now`, so a mark
 * ages the same whatever the two clocks read. An unknown schema is ignored, never guessed.
 */
export function applyBookWatchFrame(prev: BookWatchState | null, raw: unknown, nowMs: number): BookWatchState | null {
  if (!raw || typeof raw !== 'object') return prev;
  const f = raw as Record<string, unknown>;
  if (f.schema_version !== L2_BOOK_WATCH_SCHEMA_VERSION) return prev;
  const serverNow = num(f.now);
  const atOf = (ts: number) => (serverNow == null ? nowMs : nowMs - (serverNow - ts) * 1000);
  const incoming = (Array.isArray(f.drops) ? f.drops : [])
    .map(d => readDrop(d, atOf))
    .filter((d): d is HeldDrop => d !== null);
  const kept = f.reset === true || !prev ? [] : prev.drops;
  const seen = new Set(kept.map(d => d.seq));
  // Hidden sellers and buyers: one entry per stretch, its newest word winning.
  const words = new Map<string, HeldHidden>();
  for (const h of f.reset === true || !prev ? [] : prev.hidden) words.set(h.id, h);
  for (const raw of Array.isArray(f.hidden) ? f.hidden : []) {
    const h = readHidden(raw, atOf);
    const had = h ? words.get(h.id) : undefined;
    if (h && (!had || had.seq < h.seq)) words.set(h.id, h);
  }
  return {
    watching: f.watching === true,
    reason: typeof f.reason === 'string' && f.reason.trim() ? f.reason : null,
    windowSec: num(f.window_sec) ?? L2_PULLED_HERE_MEMORY_SEC,
    sides: readSides(f.sides),
    drops: [...kept, ...incoming.filter(d => !seen.has(d.seq))].filter(d => nowMs - d.atMs <= MEMORY_MS),
    hidden: [...words.values()].filter(h => hiddenAlive(h, nowMs)),
  };
}

/** Is anything on the ladder still due to fade or go? (The ladder redraws on its own while it is.) */
export function bookWatchBusy(state: BookWatchState | null, nowMs: number): boolean {
  return !!state && (state.drops.some(d => nowMs - d.atMs <= MEMORY_MS) || state.hidden.some(h => hiddenAlive(h, nowMs)));
}

function pulledTip(drops: HeldDrop[], side: BookSide, nowMs: number): { title: string; tip: string } {
  const total = drops.reduce((s, d) => s + d.pulled, 0);
  if (drops.length === 1) {
    const d = drops[0];
    const lines = [`Left the book ${secs(nowMs - d.atMs)} ago; ${d.filled > 0 ? `${whole(d.filled)} of it` : 'none of it'} traded there.`];
    const came = d.distanceAtPostTicks != null && d.distanceTicks != null ? d.distanceAtPostTicks - d.distanceTicks : null;
    const rested = d.lifetimeSec != null ? `after resting ${d.lifetimeSec.toFixed(2)} s` : null;
    if (d.onApproach && came != null) lines.push(`It was pulled as the price came ${came} tick${came === 1 ? '' : 's'} closer${rested ? `, ${rested}` : ''}.`);
    else if (rested) lines.push(`It was pulled ${rested}.`);
    if (d.levelBefore != null && d.levelAfter != null) lines.push(`${whole(d.levelBefore)} was there; ${whole(d.levelAfter)} stayed.`);
    lines.push(L2_PULLS_NOTE);
    return { title: `${whole(d.pulled)} ${SIDE_WORD[side]} at ${px(d.price)} pulled`, tip: lines.join('\n') };
  }
  const lines = drops.map(d => `${whole(d.pulled)} at ${px(d.price)}${d.onApproach ? ', pulled as the price came closer' : ''}, ${secs(nowMs - d.atMs)} ago`);
  lines.push(L2_PULLS_NOTE);
  return { title: `${whole(total)} ${SIDE_WORD[side]} pulled at ${drops.length} prices`, tip: lines.join('\n') };
}

function tradedTip(drops: HeldDrop[], side: BookSide, nowMs: number): { title: string; tip: string } {
  const total = drops.reduce((s, d) => s + d.filled, 0);
  const lines = drops.map(d => {
    const rested = d.lifetimeSec != null ? `, rested ${d.lifetimeSec.toFixed(1)} s` : '';
    const pulledToo = d.pulled > 0 ? `; ${whole(d.pulled)} pulled` : '';
    return `${whole(d.filled)} at ${px(d.price)} ${secs(nowMs - d.atMs)} ago${rested}${pulledToo}`;
  });
  lines.push('Lit prints at those prices took it.');
  return { title: `${whole(total)} ${SIDE_WORD[side]} traded`, tip: lines.join('\n') };
}

export function opacityAt(ageMs: number): number {
  const fadeFrom = L2_PULL_MARK_SHOW_MS - L2_PULL_MARK_FADE_MS;
  if (ageMs <= fadeFrom) return 1;
  return Math.max(0, Math.min(1, (L2_PULL_MARK_SHOW_MS - ageMs) / L2_PULL_MARK_FADE_MS));
}

/**
 * One side's marks among its shown rows. Every drop of the last L2_PULL_MARK_SHOW_MS is placed where its
 * price sits; drops that land between the same two rows share a mark per verdict (a sweep that took
 * three levels is one "traded" mark), and a place holding both verdicts shows them short.
 */
export function pullMarks(state: BookWatchState | null, side: BookSide, rows: readonly DepthLevel[], nowMs: number): PullMark[] {
  if (!state) return [];
  const groups = new Map<string, { before: number; beyond: boolean; traded: boolean; drops: HeldDrop[] }>();
  for (const d of state.drops) {
    const age = nowMs - d.atMs;
    if (d.side !== side || age < 0 || age >= L2_PULL_MARK_SHOW_MS) continue;
    const place = markerPlace(side, rows, d.price);
    const key = `${place.before}|${d.traded ? 'traded' : 'pulled'}`;
    const group = groups.get(key) ?? { ...place, traded: d.traded, drops: [] };
    group.drops.push(d);
    groups.set(key, group);
  }
  const perPlace = new Map<number, number>();
  for (const g of groups.values()) perPlace.set(g.before, (perPlace.get(g.before) ?? 0) + 1);
  const marks: PullMark[] = [];
  for (const g of groups.values()) {
    const drops = [...g.drops].sort((a, b) => a.seq - b.seq);
    const newest = Math.max(...drops.map(d => d.atMs));
    const short = (perPlace.get(g.before) ?? 0) > 1;
    const kind: PullMarkKind = g.traded ? 'traded' : drops.some(d => d.onApproach) ? 'approach' : 'pulled';
    const count = g.traded ? drops.reduce((s, d) => s + d.filled, 0) : drops.reduce((s, d) => s + d.pulled, 0);
    const words = g.traded ? `✓ ${shares(count)}${short ? '' : ' traded'}` : `✕ ${shares(count)}${short ? '' : ' pulled'}`;
    const { title, tip } = g.traded ? tradedTip(drops, side, nowMs) : pulledTip(drops, side, nowMs);
    marks.push({
      id: `${side}-${g.traded ? 'traded' : 'pulled'}-${drops[0].seq}`,
      kind,
      before: g.before,
      beyond: g.beyond,
      opacity: opacityAt(nowMs - newest),
      label: `${words}${g.beyond ? ' ↓' : ''}`,
      title,
      tip,
    });
  }
  // Pulled before traded where both share a place; otherwise in the side's own order.
  return marks.sort((a, b) => a.before - b.before || (a.kind === 'traded' ? 1 : 0) - (b.kind === 'traded' ? 1 : 0));
}

/**
 * The shown prices where a large pull happened in the last minute, by price key: the ladder hatches their
 * rows and tags the first one with the count, since size sitting where size was pulled is the thing to
 * know before it goes again.
 */
export function pulledHere(state: BookWatchState | null, side: BookSide, rows: readonly DepthLevel[], nowMs: number): Map<string, PulledHere> {
  const out = new Map<string, PulledHere>();
  if (!state) return out;
  const byPrice = new Map<string, HeldDrop[]>();
  for (const d of state.drops) {
    const age = nowMs - d.atMs;
    if (d.side !== side || !d.largePull || age < 0 || age > MEMORY_MS) continue;
    const key = priceKey(d.price);
    byPrice.set(key, [...(byPrice.get(key) ?? []), d]);
  }
  for (const [key, drops] of byPrice) {
    const now = rows.filter(r => priceKey(r.price) === key).reduce((s, r) => s + (r.size || 0), 0);
    if (now <= 0) continue;
    const lines = drops
      .sort((a, b) => a.atMs - b.atMs)
      .map(d => `${whole(d.pulled)} ${SIDE_WORD[side]} pulled ${secs(nowMs - d.atMs)} ago${d.filled > 0 ? `, ${whole(d.filled)} traded` : ', none traded'}${d.onApproach ? ', as the price came closer' : ''}`);
    lines.push(`${whole(now)} ${SIDE_WORD[side]} there now.`, L2_PULLS_NOTE);
    const n = drops.length;
    out.set(key, {
      count: n,
      title: `${px(drops[0].price)}: pulled here ${n === 1 ? 'once' : n === 2 ? 'twice' : `${n} times`} in the last minute`,
      tip: lines.join('\n'),
    });
  }
  return out;
}

/** One side's line above the ladder: its size pulled against its size traded over the watcher's minute. */
export function pullsLine(state: BookWatchState | null, side: BookSide): PullsLine | null {
  if (!state) return null;
  if (!state.watching || !state.sides) {
    return { watching: false, pulled: '', traded: '', hidden: '', warn: false, title: SIDE_NAME[side], tip: state.reason ?? L2_PULLS_IDLE_REASON };
  }
  const s = state.sides[side];
  const warn = s.pulled >= L2_PULLS_WARN_MIN_SHARES && s.pulled > L2_PULLS_WARN_RATIO * Math.max(s.traded, 1);
  const where = side === 'bid' ? 'the bids' : 'the offers';
  const hiddenWho = side === 'bid' ? 'buyers' : 'sellers';
  const tip = [
    `${whole(s.pulled)} shares left ${where} without trading; ${whole(s.traded)} traded there.`,
    `${s.largePulls} large pull${s.largePulls === 1 ? '' : 's'}. Amber when pulled is over ${L2_PULLS_WARN_RATIO}× traded.`,
    ...(s.hidden > 0 ? [`◆ ${whole(s.hidden)} traded beyond what the book showed, at the prices of hidden ${hiddenWho}.`] : []),
    L2_PULLS_NOTE,
  ].join('\n');
  return {
    watching: true,
    pulled: `✕ ${fmtVolume(s.pulled)}`,
    traded: `✓ ${fmtVolume(s.traded)}`,
    hidden: s.hidden > 0 ? `◆ ${fmtVolume(s.hidden)}` : '',
    warn,
    title: `${SIDE_NAME[side]}, last ${Math.round(state.windowSec)} s`,
    tip,
  };
}
