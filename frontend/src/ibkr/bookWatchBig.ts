/**
 * Big sellers and buyers on the Level 2 ladder (#984; the watcher's big_seller.py, #846). Pure: the folded
 * `book_watch` state goes in; each side's block rows and its column-head banner come out.
 *
 * While a big seller (the ask) or big buyer (the bid) holds, its rows are a dark block with a white frame and a
 * "Big seller" tag, a slate bar filling with what traded there, and the banner names it with its size, its share
 * of the float and the seconds of the last minute's lit volume it would take. With none holding, the banner says
 * how the newest one ended -- taken, pulled, pulled as the price came, or out of view -- fading out. The watcher
 * decides every word; nothing here infers a wall or a verdict, and nothing acts on one.
 */
import { L2_BIG_BACK_MIN, L2_BIG_FADE_MS, L2_BIG_NOTE, L2_BIG_SHOW_ENDED_MS } from '../constants';
import { markPrice, markShares, markWhole, priceKey, type BookSide, type BookWatchState } from './bookWatch';
import type { BigFloat, HeldBig } from './bookWatchBigRead';
import type { DepthLevel } from './types';

export type BigBannerKind = 'holding' | 'taken' | 'pulled' | 'approach' | 'lost';

/** One row of a big seller's or buyer's block. */
export interface BigRow {
  first: boolean;
  last: boolean;
  /** On the block's first row: "Big seller" / "Big buyer". */
  tag: string | null;
  /** On its last row once something traded there: traded / (traded + size now), 0..100. */
  takenPct: number | null;
  title: string;
  tip: string;
}

/**
 * A piece of the banner, written after `sep`. A narrower ladder drops them by key (level2Montage.css): `pace`
 * (seconds of volume, back again) under 750 px, `detail` under 560, `price` and `float` under 380, so the Trader
 * rail's reads "Big seller · 48.2K" or "✕ Big seller pulled". The hover always has all of it.
 */
export interface BigBannerPart {
  key: 'lead' | 'price' | 'size' | 'verdict' | 'detail' | 'float' | 'pace';
  sep: string;
  text: string;
}

export interface BigBanner {
  kind: BigBannerKind;
  parts: BigBannerPart[];
  opacity: number;
  title: string;
  tip: string;
}

const WHO: Record<BookSide, string> = { ask: 'Big seller', bid: 'Big buyer' };
const ONE: Record<BookSide, string> = { ask: 'seller', bid: 'buyer' };
const RESTING: Record<BookSide, string> = { ask: 'offered', bid: 'bid' };
const LIVE = new Set(['holding', 'left']);

function ago(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000));
  return s < 90 ? `${s} s ago` : `${Math.round(s / 60)} min ago`;
}

/** Seconds of trading in plain words: "40 s", "4.5 min", "2 h+". */
export function clearWords(sec: number): string {
  if (sec < 60) return `${Math.max(1, Math.round(sec))} s`;
  if (sec < 600) return `${(sec / 60).toFixed(1)} min`;
  if (sec < 3600) return `${Math.round(sec / 60)} min`;
  return `${Math.floor(sec / 3600)} h+`;
}

/** Its share of the float: "1.9%", "12%", "<0.1%". */
export function floatPct(size: number, float: BigFloat): string {
  const pct = (size / float.shares) * 100;
  if (pct < 0.1) return '<0.1%';
  return `${pct < 10 ? pct.toFixed(1) : Math.round(pct)}%`;
}

function ordinal(n: number): string {
  const tail = n % 100 >= 11 && n % 100 <= 13 ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' } as Record<number, string>)[n % 10] ?? 'th';
  return `${n}${tail}`;
}

function untraded(w: HeldBig): number {
  return w.left ? Math.max(0, w.left.before - w.left.after - w.left.filled) : w.sizeNow;
}

function endKind(w: HeldBig): BigBannerKind {
  if (w.state === 'eaten') return 'taken';
  if (w.state === 'pulled') return w.onApproach ? 'approach' : 'pulled';
  return 'lost';
}

/** The hover: what it is, against what, how it stands and how it ended. Ends with the note. */
export function bigTip(w: HeldBig, float: BigFloat | null, nowMs: number): string {
  const p = markPrice(w.price);
  const lines: string[] = [];
  const size = LIVE.has(w.state) ? w.sizeNow : (w.left?.before ?? w.sizeNow);
  const mult = w.multiple !== null && w.medianLevel !== null
    ? `, ${w.multiple.toFixed(1)}x the typical level on its side (${markWhole(w.medianLevel)})`
    : '';
  lines.push(`${markWhole(size)} ${RESTING[w.side]} at ${p}${mult}.`);
  lines.push(`Big since ${ago(nowMs - w.firstSeenMs)}${w.seenFromStart ? ', or longer: it was there when Nova started reading the book' : ''}.`);
  if (w.traded > 0) lines.push(`${markWhole(w.traded)} traded at ${p} since.`);
  if (float) {
    lines.push(`${floatPct(size, float)} of the float (${markShares(float.shares)} shares${float.contradicted ? '; that float may be out of date' : ''}).`);
  } else {
    lines.push('No float is known for this stock yet.');
  }
  if (LIVE.has(w.state)) {
    lines.push(w.clearSec !== null
      ? `${clearWords(w.clearSec)} of trading at the last minute's lit volume.`
      : 'No lit trades in the last minute to time it against.');
  }
  if (w.back) {
    lines.push(`A big ${ONE[w.side]} at ${p} was pulled ${w.back.pulled === 1 ? 'once' : `${w.back.pulled} times`} in the ${L2_BIG_BACK_MIN} minutes before; the last (${markShares(w.back.lastSize)}) left ${ago(nowMs - w.back.lastEndedMs)}. Not necessarily the same ${ONE[w.side]}.`);
  }
  const kind = LIVE.has(w.state) ? null : endKind(w);
  if (kind === 'taken') lines.push(`Taken: prints at ${p} took at least half of what left, or a print went through it.`);
  if (kind === 'pulled') lines.push(`Pulled: it left the book and prints at ${p} took less than half of it (${markWhole(untraded(w))} left untraded).`);
  if (kind === 'approach') lines.push(`Pulled as the price came closer to it: ${markWhole(untraded(w))} left untraded. A hint consistent with spoofing, never a detection.`);
  if (kind === 'lost') lines.push(`Out of view: the book stopped showing ${p} (past the rows shown, or the line restarted). Unknown, never called pulled.`);
  lines.push(L2_BIG_NOTE);
  return lines.join('\n');
}

/** The rows of each big seller or buyer that holds on this side, by row index. */
export function bigRows(state: BookWatchState | null, side: BookSide, rows: readonly DepthLevel[], nowMs: number): Map<number, BigRow> {
  const out = new Map<number, BigRow>();
  if (!state) return out;
  for (const w of state.big) {
    if (w.side !== side || w.state !== 'holding') continue;
    const key = priceKey(w.price);
    const at = rows.flatMap((r, i) => (priceKey(r.price) === key ? [i] : []));
    if (!at.length) continue;
    const title = `${WHO[side]} at ${markPrice(w.price)}: ${markShares(w.sizeNow)}`;
    const tip = bigTip(w, state.bigFloat, nowMs);
    const taken = w.traded > 0 ? Math.round((w.traded / (w.traded + w.sizeNow)) * 100) : null;
    at.forEach((i, n) => out.set(i, {
      first: n === 0,
      last: n === at.length - 1,
      tag: n === 0 ? WHO[side] : null,
      takenPct: n === at.length - 1 ? taken : null,
      title,
      tip,
    }));
  }
  return out;
}

function opacity(w: HeldBig, nowMs: number): number {
  if (w.endedMs === null) return 1;
  const age = nowMs - w.endedMs;
  if (age < 0) return 1;
  if (age >= L2_BIG_SHOW_ENDED_MS) return 0;
  return Math.min(1, (L2_BIG_SHOW_ENDED_MS - age) / L2_BIG_FADE_MS);
}

/** The banner over this side's column head: the nearest big seller or buyer that holds, else how the newest ended. */
export function bigBanner(state: BookWatchState | null, side: BookSide, nowMs: number): BigBanner | null {
  if (!state || !state.watching) return null;
  const mine = state.big.filter(w => w.side === side);
  const holding = mine.find(w => LIVE.has(w.state));   // the watcher lists them nearest the price first
  const ended = mine
    .filter(w => !LIVE.has(w.state) && opacity(w, nowMs) > 0)
    .sort((a, b) => (b.endedMs ?? 0) - (a.endedMs ?? 0))[0];
  const w = holding ?? ended;
  if (!w) return null;
  const float = state.bigFloat;
  const p = markPrice(w.price);
  const tip = bigTip(w, float, nowMs);
  if (holding) {
    const parts: BigBannerPart[] = [
      { key: 'lead', sep: '', text: WHO[side] },
      { key: 'price', sep: ' ', text: p },
      { key: 'size', sep: ' · ', text: markShares(w.sizeNow) },
    ];
    if (w.traded > 0) {
      parts.push({ key: 'detail', sep: ' ', text: 'left' }, { key: 'detail', sep: ' · ', text: `${markShares(w.traded)} taken` });
    }
    if (float) parts.push({ key: 'float', sep: ' · ', text: `${floatPct(w.sizeNow, float)} of float${float.contradicted ? '?' : ''}` });
    if (w.clearSec !== null) parts.push({ key: 'pace', sep: ' · ', text: `${clearWords(w.clearSec)} of lit volume` });
    if (w.back) parts.push({ key: 'pace', sep: ' · ', text: `back · ${ordinal(w.back.pulled + 1)} in ${L2_BIG_BACK_MIN} min` });
    return { kind: 'holding', parts, opacity: 1, title: `${WHO[side]} at ${p}`, tip };
  }
  const kind = endKind(w) as Exclude<BigBannerKind, 'holding'>;
  const mark: Record<typeof kind, string> = { taken: '✓ ', pulled: '✕ ', approach: '✕ ', lost: '' };
  const verdict: Record<typeof kind, string> = { taken: 'taken', pulled: 'pulled', approach: 'pulled', lost: 'out of view' };
  const result: Record<typeof kind, string> = {
    taken: `${markShares(w.traded)} traded`,
    pulled: `${markShares(untraded(w))} untraded`,
    approach: `${markShares(untraded(w))} untraded`,
    lost: 'unknown',
  };
  const parts: BigBannerPart[] = [
    { key: 'lead', sep: '', text: `${mark[kind]}${WHO[side]}` },
    { key: 'price', sep: ' ', text: p },
    { key: 'verdict', sep: ' ', text: verdict[kind] },
  ];
  if (kind === 'approach') parts.push({ key: 'detail', sep: ' ', text: 'as price came' });
  parts.push({ key: 'detail', sep: ' · ', text: result[kind] });
  return { kind, parts, opacity: opacity(w, nowMs), title: `${WHO[side]} at ${p}`, tip };
}
