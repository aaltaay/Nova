/**
 * The Activity column: every open, add and close of the day, newest first, built from the day's trades (the feed's
 * events are not read). A close the feed never saw makes no row; a position already open when capture started is
 * "holding". Pure.
 */
import { FT_ALREADY_OPEN } from './constants';
import { etTime, held, price } from './format';
import type { FollowedTicker, FollowedTrade, FollowedTrader } from './types';

export type ActivityVerb = 'opened' | 'holding' | 'added to' | 'closed';

export interface ActivityItem {
  key: string;
  ts: number;
  trader: string;
  verb: ActivityVerb;
  side: FollowedTrade['side'];
  symbol: string;
  /** The trade's ticker check, for its mark: a ticker the feed may have read glued to its price. */
  ticker: FollowedTicker | null;
  price: number | null;
  note: string | null;
  /** This API's evidence path, or null. */
  image: string | null;
  tradeId: string;
}

function windowNote(from: number | null, to: number): string | null {
  return from === null ? null : `Somewhere between ${etTime(from)} and ${etTime(to)}`;
}

export function tradeActivity(t: FollowedTrade): ActivityItem[] {
  const base = { trader: t.trader, side: t.side, symbol: t.symbol, ticker: t.ticker ?? null, tradeId: t.id };
  const out: ActivityItem[] = [{
    ...base,
    key: `${t.id}|in`,
    ts: t.entry.ts,
    verb: t.entry.known ? 'opened' : 'holding',
    price: t.entry.first_price,
    note: t.entry.known ? windowNote(t.entry.since_ts, t.entry.ts) : FT_ALREADY_OPEN,
    image: t.evidence.entry,
  }];
  t.adds.forEach((a, i) => {
    out.push({
      ...base,
      key: `${t.id}|add${i}`,
      ts: a.ts,
      verb: 'added to',
      price: a.price,
      note: a.prev_price === null ? null : `Average ${price(a.prev_price)} → ${price(a.price)}`,
      image: null,
    });
  });
  if (t.status === 'closed' && t.exit && t.exit.to_ts !== null) {
    const notes = [`Held ${held(t.held)}`];
    const win = windowNote(t.exit.from_ts, t.exit.to_ts);
    if (win) notes.push(win);
    out.push({
      ...base,
      key: `${t.id}|out`,
      ts: t.exit.to_ts,
      verb: 'closed',
      price: null,
      note: notes.join(' · '),
      image: t.evidence.exit,
    });
  }
  return out;
}

export function activity(traders: FollowedTrader[]): ActivityItem[] {
  const items = traders.flatMap((tr) => [...tr.open, ...tr.closed].flatMap(tradeActivity));
  // Newest first; at the same second a close reads above the open it made room for.
  const rank: Record<ActivityVerb, number> = { closed: 0, 'added to': 1, opened: 2, holding: 3 };
  return items.sort((a, b) => b.ts - a.ts || rank[a.verb] - rank[b.verb]);
}
