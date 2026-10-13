/**
 * How fresh the market on screen is, per symbol, and the view every order carries (ADR 045).
 *
 * "If it lags, then we cannot place an order." The Level 2 socket reports every frame here (no React
 * render): `subscribed` names the backend process, a `book` carries its version (`seq`, `at`) and when
 * it was `sent`, a `beat` says the newest version as of the backend's `now`. The ladder reports which
 * version it has drawn (`noteBookShown`), and the quote stream its `trade_update` versions.
 *
 * A symbol's view is behind -- and its order controls lock -- while its Level 2 has had no word from
 * the backend for `VIEW_SILENT_LOCK_MS`, its last frame took more than `VIEW_TRANSIT_LOCK_MS` to
 * arrive, or a newer book has waited more than `VIEW_UNDRAWN_LOCK_MS` to be drawn. `viewStampFor` is
 * what the order says it was priced from; the backend judges it again and refuses a stale one.
 *
 * A Level 2 IBKR refused or ended (the socket's `error`) is no Level 2 at all, not a late one: its
 * orders lock steadily, with IBKR's reason, until a book arrives (operator decision 2026-10-13, #913).
 * On 2026-10-13 a refused line instead read "behind" and flipped open and locked every 1.2 s, because
 * each retry's `subscribed` restarted the silence clock. Every flip is reported to the backend log.
 *
 * In memory, per window. Desk and backend run on one machine (the backend binds 127.0.0.1), so the
 * backend's `sent` / `now` and this window's `Date.now()` are one clock.
 */
import {
  LEVEL2_REFUSED_LEAD,
  LEVEL2_REFUSED_TAIL,
  TICKET_LEVEL2_REFUSED_LABEL,
  TICKET_VIEW_LOCKED_LABEL,
  VIEW_LOCK_TAIL,
  VIEW_LOCK_TICK_MS,
  VIEW_SILENT_LOCK_MS,
  VIEW_TRANSIT_LOCK_MS,
  VIEW_UNDRAWN_LOCK_MS,
} from '../constantGroups/market_view';

interface BookView {
  instance: string | null;
  /** The newest version this window knows of: from a book frame or a beat. */
  latestSeq: number | null;
  /** The newest book frame received: its version and when it was applied (backend clock). */
  receivedSeq: number | null;
  /** When the backend last spoke on this line (a book or a beat), on this window's clock. */
  lastWordWall: number | null;
  /** The last book frame's `sent` to its arrival, ms. */
  transitMs: number | null;
  /** The version the ladder drew, its `at`, and the top of book it showed. */
  shownSeq: number | null;
  shownAt: number | null;
  shownBid: number | null;
  shownAsk: number | null;
  /** Since when (this window's clock) a newer version than the drawn one has been known. */
  behindSince: number | null;
  /** `at` of each version received, for the drawn version's stamp. */
  atBySeq: Map<number, number | null>;
  /** IBKR refused or ended this Level 2 (the socket's `error` message); cleared by the next book. */
  refused: string | null;
}

interface QuoteView {
  seq: number;
  at: number | null;
  price: number | null;
}

export interface ViewStamp {
  schema_version: 1;
  symbol: string;
  action_wall_ms: number;
  instance: string | null;
  book: { seq: number; at: number | null; bid: number | null; ask: number | null } | null;
  quote: { seq: number; at: number | null; price: number | null } | null;
  desk: { silent_ms: number | null; transit_ms: number | null; undrawn_ms: number | null } | null;
}

const books = new Map<string, BookView>();
const quotes = new Map<string, QuoteView>();
const AT_KEEP = 64;

function key(symbol: string): string {
  return symbol.trim().toUpperCase();
}

function num(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function bookFor(symbol: string): BookView {
  const k = key(symbol);
  let view = books.get(k);
  if (!view) {
    view = {
      instance: null, latestSeq: null, receivedSeq: null, lastWordWall: null, transitMs: null,
      shownSeq: null, shownAt: null, shownBid: null, shownAsk: null, behindSince: null, atBySeq: new Map(),
      refused: null,
    };
    books.set(k, view);
  }
  return view;
}

function noteLatest(view: BookView, seq: number | null, wall: number): void {
  if (seq == null) return;
  if (view.latestSeq == null || seq > view.latestSeq) view.latestSeq = seq;
  if (view.shownSeq != null && view.latestSeq > view.shownSeq) {
    view.behindSince ??= wall;
  }
}

/** The Level 2 socket subscribed: which backend process its frames come from. */
export function noteSubscribed(symbol: string, instance: unknown, wall = Date.now()): void {
  const view = bookFor(symbol);
  view.instance = typeof instance === 'string' ? instance : null;
  view.lastWordWall = wall;
}

/** A `book` frame arrived. */
export function noteBookFrame(
  symbol: string,
  frame: { seq?: unknown; at?: unknown; sent?: unknown },
  wall = Date.now(),
): void {
  const view = bookFor(symbol);
  const seq = num(frame.seq);
  const sent = num(frame.sent);
  view.lastWordWall = wall;
  view.refused = null; // a book proves the line
  view.transitMs = sent != null ? Math.max(0, wall - sent * 1000) : null;
  if (seq != null) {
    view.receivedSeq = seq;
    view.atBySeq.set(seq, num(frame.at));
    if (view.atBySeq.size > AT_KEEP) {
      const oldest = view.atBySeq.keys().next().value;
      if (oldest !== undefined) view.atBySeq.delete(oldest);
    }
  }
  noteLatest(view, seq, wall);
}

/**
 * IBKR refused or ended the symbol's Level 2 (the socket's `error`). Its orders lock with this reason until a
 * book arrives -- a retry's `subscribed` does not clear it, since IBKR answers after the backend says it.
 */
export function noteRefused(symbol: string, message: string): void {
  bookFor(symbol).refused = message.trim() || 'IBKR ended this Level 2.';
}

/** A `beat` arrived: the line's newest version as of the backend's `now`. */
export function noteBeat(symbol: string, frame: { seq?: unknown; now?: unknown }, wall = Date.now()): void {
  const view = bookFor(symbol);
  view.lastWordWall = wall;
  const now = num(frame.now);
  // A beat that took long to arrive says the socket is behind, just like a slow book frame.
  if (now != null) view.transitMs = Math.max(0, wall - now * 1000);
  const seq = num(frame.seq);
  noteLatest(view, seq != null && seq > 0 ? seq : null, wall);
}

/** The ladder drew this book version (after the commit, before paint). */
export function noteBookShown(
  symbol: string,
  seq: number | null | undefined,
  bid: number | null,
  ask: number | null,
): void {
  if (seq == null || !Number.isFinite(seq)) return;
  const view = bookFor(symbol);
  view.shownSeq = seq;
  view.shownAt = view.atBySeq.get(seq) ?? null;
  view.shownBid = bid;
  view.shownAsk = ask;
  if (view.latestSeq == null || seq >= view.latestSeq) view.behindSince = null;
}

/** A `trade_update` arrived on the quote stream. */
export function noteQuote(symbol: string, frame: { seq?: unknown; at?: unknown; price?: unknown }): void {
  const seq = num(frame.seq);
  if (seq == null) return;
  quotes.set(key(symbol), { seq, at: num(frame.at), price: num(frame.price) });
}

/** This window stopped showing the symbol's Level 2 (another symbol, or unmounted). */
export function forgetBook(symbol: string): void {
  books.delete(key(symbol));
  recompute();
}

function secs(ms: number): string {
  return `${(ms / 1000).toFixed(1)} s`;
}

/** Why orders on *symbol* are locked now, or null while its view is live (or not judged here). */
export function viewLockReason(symbol: string | null | undefined, now = Date.now()): string | null {
  if (!symbol) return null;
  const view = books.get(key(symbol));
  if (!view) return null;                                   // no Level 2 for it here: the backend judges
  if (view.refused != null) {
    return `${LEVEL2_REFUSED_LEAD} ${key(symbol)}: ${view.refused} ${LEVEL2_REFUSED_TAIL}`;
  }
  if (view.lastWordWall == null) return null;
  const silent = now - view.lastWordWall;
  if (silent > VIEW_SILENT_LOCK_MS) {
    return `Level 2 is behind the market: no word from Nova for ${secs(silent)}. ${VIEW_LOCK_TAIL}`;
  }
  if (view.transitMs != null && view.transitMs > VIEW_TRANSIT_LOCK_MS) {
    return `Level 2 is behind the market: its last update took ${secs(view.transitMs)} to arrive. ${VIEW_LOCK_TAIL}`;
  }
  if (view.behindSince != null && now - view.behindSince > VIEW_UNDRAWN_LOCK_MS) {
    return `Level 2 is behind the market: the desk has not drawn its newest book for ${secs(now - view.behindSince)}. ${VIEW_LOCK_TAIL}`;
  }
  return null;
}

/** The order button's words for a lock reason: no Level 2, or a Level 2 behind the market. */
export function viewLockLabel(why: string): string {
  return why.startsWith(LEVEL2_REFUSED_LEAD) ? TICKET_LEVEL2_REFUSED_LABEL : TICKET_VIEW_LOCKED_LABEL;
}

/** What an order says it was priced from (ADR 045): the moment and the versions on screen. */
export function viewStampFor(symbol: string, actionWallMs: number, now = Date.now()): ViewStamp {
  const k = key(symbol);
  const view = books.get(k);
  const quote = quotes.get(k);
  return {
    schema_version: 1,
    symbol: k,
    action_wall_ms: actionWallMs,
    instance: view?.instance ?? null,
    book: view && view.shownSeq != null
      ? { seq: view.shownSeq, at: view.shownAt, bid: view.shownBid, ask: view.shownAsk }
      : null,
    quote: quote ? { seq: quote.seq, at: quote.at, price: quote.price } : null,
    desk: view
      ? {
          silent_ms: view.lastWordWall != null ? Math.max(0, now - view.lastWordWall) : null,
          transit_ms: view.transitMs,
          undrawn_ms: view.behindSince != null ? Math.max(0, now - view.behindSince) : 0,
        }
      : null,
  };
}

// ── lock readers: one timer while anything reads, a change only when a lock flips ──

const listeners = new Set<() => void>();
const locks = new Map<string, string | null>();
const lockedSince = new Map<string, number>();
let timer: ReturnType<typeof setInterval> | null = null;
type LockFlip = (symbol: string, why: string | null, lockedForMs: number | null) => void;
let reportFlip: LockFlip | null = null;

/** Who hears each lock flip (the backend log reporter, `lockReport.ts`); null to stop. */
export function onViewLockFlip(fn: LockFlip | null): void {
  reportFlip = fn;
}

function flipped(k: string, why: string | null, now: number): void {
  let lockedFor: number | null = null;
  if (why != null) {
    lockedSince.set(k, lockedSince.get(k) ?? now);
  } else {
    const since = lockedSince.get(k);
    lockedFor = since != null ? now - since : null;
    lockedSince.delete(k);
  }
  try {
    reportFlip?.(k, why, lockedFor);
  } catch (err) {
    console.debug('[Nova] view lock report failed', err);
  }
}

function sameLock(prev: string | null, next: string | null): boolean {
  // A lock's words carry a count of seconds: readers change only when it flips between locked and live,
  // or between no Level 2 and a Level 2 behind (the button says which).
  if (prev == null || next == null) return prev == null && next == null;
  return viewLockLabel(prev) === viewLockLabel(next);
}

function recompute(now = Date.now()): void {
  let changed = false;
  const seen = new Set<string>();
  for (const k of books.keys()) {
    seen.add(k);
    const next = viewLockReason(k, now);
    const prev = locks.get(k) ?? null;
    if (!sameLock(prev, next)) {
      locks.set(k, next);
      changed = true;
      flipped(k, next, now);
    }
  }
  for (const k of [...locks.keys()]) {
    if (!seen.has(k)) {
      if (locks.get(k) != null) {
        changed = true;
        flipped(k, null, now);
      }
      locks.delete(k);
    }
  }
  if (changed) listeners.forEach((listener) => listener());
}

/** Subscribe to lock flips (for `useSyncExternalStore`). */
export function subscribeViewLocks(listener: () => void): () => void {
  listeners.add(listener);
  if (timer == null) timer = setInterval(() => recompute(), VIEW_LOCK_TICK_MS);
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0 && timer != null) {
      clearInterval(timer);
      timer = null;
    }
  };
}

/** The lock as last judged by the timer (stable between flips). */
export function currentViewLock(symbol: string | null | undefined): string | null {
  return symbol ? locks.get(key(symbol)) ?? null : null;
}

export function resetViewRegistryForTests(): void {
  books.clear();
  quotes.clear();
  locks.clear();
  lockedSince.clear();
  reportFlip = null;
  listeners.clear();
  if (timer != null) clearInterval(timer);
  timer = null;
}

/** Re-judge now (tests, and a reader that must not wait a tick). */
export function recomputeViewLocks(now = Date.now()): void {
  recompute(now);
}
