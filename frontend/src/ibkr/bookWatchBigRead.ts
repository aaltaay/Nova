/**
 * Big sellers and buyers in the depth socket's `book_watch` frames (#984), read: the watcher's whole list of the
 * line's walls (backend/book_watch/big_seller.py) and the float Nova already read for the symbol. Pure; nothing
 * here infers a wall or a verdict. A frame without `big` (an older backend, or one with nothing new about them)
 * leaves the list as it was; bookWatchBig.ts draws it.
 */
import type { BookSide } from './bookWatch';

export type BigState = 'holding' | 'left' | 'eaten' | 'pulled' | 'lost';
const STATES: ReadonlySet<string> = new Set<BigState>(['holding', 'left', 'eaten', 'pulled', 'lost']);

export interface HeldBig {
  id: string;
  side: BookSide;
  price: number;
  state: BigState;
  sizeNow: number;
  traded: number;
  multiple: number | null;
  medianLevel: number | null;
  /** Its size over the last minute's lit volume, in seconds; null with no pace (or once it ended). */
  clearSec: number | null;
  /** Pulled as the price came closer to it. */
  onApproach: boolean;
  /** Walls pulled at this price in the minutes before it was called; never a claim it is the same order. */
  back: { pulled: number; lastEndedMs: number; lastSize: number } | null;
  left: { before: number; after: number; filled: number } | null;
  /** The watcher's word for how it ended: `through` (a print went through its price), `traded` (prints at its
   * price took at least half of what left), `no_prints`, or why it went out of view; null while it holds. */
  how: string | null;
  /** Big in the first book Nova read: it may have been there longer. */
  seenFromStart: boolean;
  /** When it was first seen big and, once it ended, when -- on this page's clock. */
  firstSeenMs: number;
  endedMs: number | null;
}

export interface BigFloat {
  shares: number;
  /** The scanner's `float_contradicted`: Yahoo's float may be out of date. */
  contradicted: boolean;
}

export interface BigFold {
  big: HeldBig[];
  bigFloat: BigFloat | null;
}

export const NO_BIG: BigFold = { big: [], bigFloat: null };

function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

function obj(v: unknown): Record<string, unknown> | null {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
}

function readWall(raw: unknown, atOf: (ts: number) => number): HeldBig | null {
  const w = obj(raw);
  const price = num(w?.price);
  const firstSeen = num(w?.first_seen_ts);
  if (!w || price === null || firstSeen === null || typeof w.id !== 'string') return null;
  if ((w.side !== 'bid' && w.side !== 'ask') || typeof w.state !== 'string' || !STATES.has(w.state)) return null;
  const back = obj(w.back);
  const left = obj(w.left);
  const ended = num(w.ended_ts);
  const backEnded = num(back?.last_ended_ts);
  return {
    id: w.id,
    side: w.side,
    price,
    state: w.state as BigState,
    sizeNow: num(w.size_now) ?? 0,
    traded: num(w.traded) ?? 0,
    multiple: num(w.multiple),
    medianLevel: num(w.median_level),
    clearSec: num(w.clear_sec),
    onApproach: w.on_approach === true,
    back: back && backEnded !== null
      ? { pulled: num(back.pulled) ?? 1, lastEndedMs: atOf(backEnded), lastSize: num(back.last_size) ?? 0 }
      : null,
    left: left ? { before: num(left.before) ?? 0, after: num(left.after) ?? 0, filled: num(left.filled) ?? 0 } : null,
    how: typeof w.how === 'string' ? w.how : null,
    seenFromStart: w.seen_from_start === true,
    firstSeenMs: atOf(firstSeen),
    endedMs: ended === null ? null : atOf(ended),
  };
}

function readFloat(raw: unknown): BigFloat | null {
  const f = obj(raw);
  const shares = num(f?.shares);
  return f && shares !== null && shares > 0 ? { shares, contradicted: f.contradicted === true } : null;
}

/** The frame's walls and float, or `prev` when the frame says nothing about them. */
export function readBigFrame(f: Record<string, unknown>, atOf: (ts: number) => number, prev: BigFold): BigFold {
  if (!Array.isArray(f.big)) return prev;
  return {
    big: f.big.map(w => readWall(w, atOf)).filter((w): w is HeldBig => w !== null),
    bigFloat: readFloat(f.big_float),
  };
}
