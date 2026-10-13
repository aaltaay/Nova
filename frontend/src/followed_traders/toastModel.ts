/**
 * Which trade toasts one answer of the day raises against the one before: a trade first seen opens, an add raises
 * "added to", open to closed raises "closed". The first answer of a day raises none (it is what was already there),
 * and a position already open when capture started never raises "opened". Pure.
 */
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
}

function allTrades(day: FollowedDay): { trade: FollowedTrade; face: string | null }[] {
  return day.traders.flatMap((t) => [...t.open, ...t.closed].map((trade) => ({ trade, face: t.face })));
}

export function tradeToasts(prev: FollowedDay | null, next: FollowedDay): TradeToast[] {
  if (!prev || !next.date || prev.date !== next.date || prev.feed.state !== 'ok' || next.feed.state !== 'ok') return [];
  const date = next.date;
  const before = new Map(allTrades(prev).map(({ trade }) => [trade.id, trade]));
  const out: TradeToast[] = [];
  for (const { trade: t, face } of allTrades(next)) {
    const base = { trader: t.trader, side: t.side, symbol: t.symbol, tradeId: t.id, date, face };
    const old = before.get(t.id);
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
  return out.sort((a, b) => a.ts - b.ts);
}
