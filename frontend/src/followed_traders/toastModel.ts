/**
 * Which trade toasts one answer of the day raises against the one before: a trade first seen opens, an add raises
 * "added to", open to closed raises "closed". The first answer of a day raises none (it is what was already there),
 * and a position already open when capture started never raises "opened". A trade first seen while its ticker is being
 * checked (the feed may have read it glued to its price) is held back until the check ends or
 * FOLLOWED_TOAST_TICKER_WAIT_SEC has passed since its entry, so its toast names the ticker as checked; the caller keeps
 * the held trades between answers (`toastStep`), so a trade already seen is never news twice. Pure.
 */
import { FOLLOWED_TOAST_TICKER_WAIT_SEC, FT_TICKER_CHECK } from './constants';
import { tickerUnsettled } from './ticker';
import type { FollowedDay, FollowedTrade } from './types';

export type ToastVerb = 'opened' | 'added to' | 'closed';

export interface TradeToast {
  key: string;
  verb: ToastVerb;
  trader: string;
  side: FollowedTrade['side'];
  symbol: string;
  /** The price on the bar (entry, or the new average); null for a close (the bar shows none). */
  price: number | null;
  ts: number;
  tradeId: string;
  date: string;
  face: string | null;
  /** Why the ticker may be wrong (still checking, or neither reading fits IBKR's tape); null when it is settled. */
  check: string | null;
}

function allTrades(day: FollowedDay): { trade: FollowedTrade; face: string | null }[] {
  return day.traders.flatMap((t) => [...t.open, ...t.closed].map((trade) => ({ trade, face: t.face })));
}

/** The trade's ticker is still being checked, as of `at`, and not for long enough to stop waiting for it. */
function waiting(t: FollowedTrade, at: number): boolean {
  return t.ticker?.state === 'checking' && at - t.entry.ts < FOLLOWED_TOAST_TICKER_WAIT_SEC;
}

const NONE: ReadonlySet<string> = new Set();

/** One answer's toasts, and the trades held back for their ticker check, to pass with the next answer. */
export interface ToastStep {
  toasts: TradeToast[];
  /** Ids of trades first seen while their ticker was being checked and not announced yet: news once it settles. */
  held: ReadonlySet<string>;
}

/** The toasts `next` raises against `prev`. `held` is the last step's: a trade it holds is still news, while every
 *  other trade `prev` had was already there or announced, and is never news again because its ticker is checked once
 *  more (the feed corrected it, or a restart forgot an answer). */
export function toastStep(prev: FollowedDay | null, next: FollowedDay, held: ReadonlySet<string> = NONE): ToastStep {
  if (!prev || !next.date || prev.date !== next.date || prev.feed.state !== 'ok' || next.feed.state !== 'ok') {
    return { toasts: [], held: NONE };
  }
  const date = next.date;
  const before = new Map(allTrades(prev).filter(({ trade }) => !held.has(trade.id)).map(({ trade }) => [trade.id, trade]));
  const out: TradeToast[] = [];
  const stillHeld = new Set<string>();
  for (const { trade: t, face } of allTrades(next)) {
    const old = before.get(t.id);
    if (!old && waiting(t, next.generated_at)) {
      stillHeld.add(t.id);
      continue;
    }
    const check = tickerUnsettled(t) ? t.ticker?.why ?? FT_TICKER_CHECK : null;
    const base = { trader: t.trader, side: t.side, symbol: t.symbol, tradeId: t.id, date, face, check };
    if (!old && t.entry.known) {
      out.push({ ...base, key: `${t.id}|in`, verb: 'opened', price: t.entry.first_price, ts: t.entry.ts });
    }
    for (let i = old ? old.adds.length : 0; i < t.adds.length; i += 1) {
      const a = t.adds[i];
      out.push({ ...base, key: `${t.id}|add${i}`, verb: 'added to', price: a.price, ts: a.ts });
    }
    if (t.status === 'closed' && (!old || old.status === 'open')) {
      out.push({ ...base, key: `${t.id}|out`, verb: 'closed', price: null, ts: t.exit?.to_ts ?? next.generated_at });
    }
  }
  return { toasts: out.sort((a, b) => a.ts - b.ts), held: stillHeld };
}

/** The toasts alone (`toastStep`), for a caller that keeps no trades held back. */
export function tradeToasts(prev: FollowedDay | null, next: FollowedDay, held: ReadonlySet<string> = NONE): TradeToast[] {
  return toastStep(prev, next, held).toasts;
}
