/**
 * A big seller on the ask -- for a short, a big buyer on the bid -- of the held Level 2 line (#846; the
 * operator's material lists "big sellers on the ask" as a reason to get out), pure: the reading the trade
 * you hold polls every second (`/api/book-watch/{symbol}/big-sellers`, `book_watch/big_read.py`) and its
 * words for the held card's line and the chart's call.
 *
 * Shown, never acted on: no order, no stop move, no gate. With no depth line, a stale one, the watcher off or
 * nothing recorded on a replay, the line says so in the backend's own words -- never an empty call; and with
 * a fresh line and nothing big, it says that too.
 */
import { fmtPx } from './planMath';
import { num, obj, str } from './normalize';
import { hhmmssEt } from './timeWords';

export type BigState = 'holding' | 'left' | 'eaten' | 'pulled' | 'lost';
const STATES: ReadonlySet<string> = new Set<BigState>(['holding', 'left', 'eaten', 'pulled', 'lost']);

export interface BigWall {
  id: string;
  side: 'ask' | 'bid';
  price: number;
  state: BigState;
  sizeFirst: number;
  sizeNow: number;
  traded: number;
  multiple: number | null;
  firstSeenTs: number;
  /** Big in the first book Nova read: it may have been there longer. */
  seenFromStart: boolean;
  calledTs: number | null;
  endedTs: number | null;
  heldSec: number;
  /** How far past the price: over it for a seller, under it for a buyer; 0 or less is at the price. */
  distance: number | null;
  how: string | null;
  left: { before: number; after: number; filled: number } | null;
}

export interface BigWalls {
  symbol: string;
  source: 'live' | 'replay';
  asOf: number;
  watching: boolean;
  /** Why there is no read, in plain words; null while watching. */
  reason: string | null;
  last: number | null;
  /** How far past the price a big size is looked for, in dollars. */
  window: number | null;
  sellers: BigWall[];
  buyers: BigWall[];
  /** Levels in view on each side, and whether that is enough to weigh a size against. */
  sides: Record<'ask' | 'bid', { levels: number; enough: boolean }> | null;
}

function normalizeWall(raw: unknown): BigWall | null {
  const w = obj(raw);
  const price = num(w?.price);
  const state = str(w?.state);
  const firstSeen = num(w?.first_seen_ts);
  if (!w || price === null || !state || !STATES.has(state) || firstSeen === null) return null;
  const left = obj(w.left);
  return {
    id: str(w.id) ?? `${w.side}:${price}:${firstSeen}`,
    side: w.side === 'bid' ? 'bid' : 'ask',
    price,
    state: state as BigState,
    sizeFirst: num(w.size_first) ?? 0,
    sizeNow: num(w.size_now) ?? 0,
    traded: num(w.traded) ?? 0,
    multiple: num(w.multiple),
    firstSeenTs: firstSeen,
    seenFromStart: w.seen_from_start === true,
    calledTs: num(w.called_ts),
    endedTs: num(w.ended_ts),
    heldSec: num(w.held_sec) ?? 0,
    distance: num(w.distance),
    how: str(w.how),
    left: left ? { before: num(left.before) ?? 0, after: num(left.after) ?? 0, filled: num(left.filled) ?? 0 } : null,
  };
}

function walls(raw: unknown): BigWall[] {
  return Array.isArray(raw) ? raw.map(normalizeWall).filter((w): w is BigWall => w !== null) : [];
}

function side(raw: unknown): { levels: number; enough: boolean } {
  const s = obj(raw);
  return { levels: num(s?.levels) ?? 0, enough: s?.enough === true };
}

/** Wire -> reading; null for a payload that is not one (or an unknown schema). */
export function normalizeBigWalls(raw: unknown): BigWalls | null {
  const r = obj(raw);
  const asOf = num(r?.as_of);
  if (!r || r.schema_version !== 1 || asOf === null || typeof r.watching !== 'boolean') return null;
  const sides = obj(r.sides);
  return {
    symbol: str(r.symbol) ?? '',
    source: r.source === 'replay' ? 'replay' : 'live',
    asOf,
    watching: r.watching,
    reason: str(r.reason),
    last: num(r.last),
    window: num(r.window),
    sellers: walls(r.sellers),
    buyers: walls(r.buyers),
    sides: sides ? { ask: side(sides.ask), bid: side(sides.bid) } : null,
  };
}

// -- words --------------------------------------------------------------------------------------------

const WORDS = {
  long: { who: 'BIG SELLER', side: 'ask', what: 'offered', past: 'over', others: 'asks', taker: 'bought',
    gone: 'The seller is gone.' },
  short: { who: 'BIG BUYER', side: 'bid', what: 'bid', past: 'under', others: 'bids', taker: 'sold',
    gone: 'The buyer is gone.' },
} as const;

export type BigTone = 'warn' | 'good' | 'info' | 'quiet' | 'absent';

export interface BigLine {
  tone: BigTone;
  /** One line on the card. */
  text: string;
  /** Everything else, on hover. */
  detail: string;
  wall: BigWall | null;
}

export function fmtShares(n: number): string {
  return Math.round(n).toLocaleString('en-US');
}

/** "3¢ over", "0.40¢ over" on a sub-dollar stock, "at the price". */
export function pastWords(distance: number | null, price: number, past: string): string {
  if (distance === null) return '';
  if (distance <= 1e-6) return 'at the price';
  const cents = distance * 100;
  return `${price < 1 ? cents.toFixed(2) : Math.round(cents)}¢ ${past}`;
}

/** "42 s", "3 min", "3 min+" when it was there before Nova's first book. */
export function heldWords(sec: number, plus: boolean): string {
  const s = Math.max(0, Math.round(sec));
  const text = s < 60 ? `${s} s` : `${Math.floor(s / 60)} min`;
  return plus ? `${text}+` : text;
}

/** The one a held trade is told about: the nearest still there, else the newest that ended. */
export function pickWall(list: BigWall[]): BigWall | null {
  const there = list.filter(w => w.state === 'holding' || w.state === 'left');
  if (there.length) return there[0];
  const ended = list.filter(w => w.endedTs !== null).sort((a, b) => (b.endedTs ?? 0) - (a.endedTs ?? 0));
  return ended[0] ?? null;
}

function endedWords(w: BigWall, short: boolean): { text: string; detail: string; tone: BigTone } {
  const W = short ? WORDS.short : WORDS.long;
  const at = `${W.who} @ ${fmtPx(w.price)}`;
  const size = fmtShares(w.sizeFirst);
  if (w.state === 'eaten') {
    const how = w.how === 'through'
      ? `A print went through ${fmtPx(w.price)} at ${hhmmssEt(w.endedTs)}: the size ${W.what} there traded.`
      : `${fmtShares(w.left?.filled ?? w.traded)} of the ${fmtShares(w.left ? w.left.before - w.left.after : w.sizeNow)}`
        + ` that left traded at ${fmtPx(w.price)}.`;
    // Taken: for a long, buyers took the seller out (good news); for a short, sellers took the buyer out.
    return { tone: 'good', text: `${at} TAKEN`, detail: `${how} ${W.gone} First seen at ${size}.` };
  }
  if (w.state === 'pulled') {
    const left = w.left ? fmtShares(w.left.before - w.left.after) : fmtShares(w.sizeNow);
    const traded = fmtShares(w.left?.filled ?? 0);
    return { tone: 'info', text: `${at} PULLED`, detail: `The ${left} ${W.what} at ${fmtPx(w.price)} left the book with `
      + `${traded} traded there: pulled, not ${W.taker}. It may come back.` };
  }
  const why = w.how === 'reset' ? 'the book restarted' : w.how === 'collapsed' ? 'that side of the book emptied at once'
    : 'it scrolled past the rows Level 2 shows';
  return { tone: 'info', text: `${at} · OUT OF VIEW`, detail: `Level 2 stopped showing ${fmtPx(w.price)} (${why}): `
    + 'whether it traded or was pulled is unknown.' };
}

/** The card's line about big sellers (big buyers for a short): the call, that none is there, or why there is no
 * read. ``error`` is the poll's own failure; null data with no error is the first read on its way. */
export function bigLine(r: BigWalls | null, short: boolean, error: string | null = null): BigLine {
  const W = short ? WORDS.short : WORDS.long;
  if (!r) {
    return error
      ? { tone: 'absent', text: `No read on ${W.who.toLowerCase()}s`, detail: error, wall: null }
      : { tone: 'quiet', text: `Reading Level 2 for ${W.who.toLowerCase()}s…`, detail: '', wall: null };
  }
  if (!r.watching) {
    return { tone: 'absent', text: `No read on ${W.who.toLowerCase()}s`, detail: r.reason ?? 'No Level 2 line.', wall: null };
  }
  const w = pickWall(short ? r.buyers : r.sellers);
  if (!w) {
    const s = r.sides?.[W.side] ?? null;
    if (s && !s.enough) {
      return { tone: 'quiet', text: `Too few ${W.others} on Level 2 to tell a ${W.who.toLowerCase()} (${s.levels} shown)`,
        detail: 'A big size is weighed against the levels around it; with this few there is nothing to weigh it against.',
        wall: null };
    }
    const within = r.window !== null ? ` within ${pastWords(r.window, r.last ?? 1, W.past)} the price` : '';
    return { tone: 'quiet', text: `No ${W.who.toLowerCase()}${within}`, wall: null,
      detail: `Nothing resting on the ${W.side} is several times the book around it${within}.` };
  }
  if (w.state === 'holding' || w.state === 'left') {
    const past = pastWords(w.distance, w.price, W.past);
    const held = heldWords(w.heldSec, w.seenFromStart);
    const head = `${W.who} ${fmtShares(w.sizeNow)} @ ${fmtPx(w.price)}`;
    const mult = w.multiple !== null ? `, ${w.multiple.toFixed(0)}x the other ${W.others}` : '';
    const traded = w.traded > 0 ? ` ${fmtShares(w.traded)} traded there so far.` : '';
    const since = w.seenFromStart ? `there before ${hhmmssEt(w.firstSeenTs)}` : `there since ${hhmmssEt(w.firstSeenTs)}`;
    const detail = `${fmtShares(w.sizeNow)} shares ${W.what} at ${fmtPx(w.price)}${mult}, ${past}; ${since}, first seen at `
      + `${fmtShares(w.sizeFirst)}.${traded} Shown, never acted on.`;
    if (w.state === 'left') {
      return { tone: 'warn', text: `${W.who} @ ${fmtPx(w.price)} · LEFT THE BOOK`, wall: w,
        detail: 'The book shows it gone; the tape says within a second whether it traded or was pulled.' };
    }
    return { tone: 'warn', text: `${head} · ${past} · held ${held}`, detail, wall: w };
  }
  return { ...endedWords(w, short), wall: w };
}
