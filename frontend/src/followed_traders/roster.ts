/**
 * Who the Following page shows, in order, and with what: on the feed's today everyone on the bar (`capture.bar`, the
 * bar's order) and then anyone else who traded that day; on a past day those who traded. Each comes with their photo,
 * their bar slot and their trades. Pure.
 */
import type { FollowedBarSlot, FollowedDay, FollowedTrader } from './types';

export interface RosterEntry {
  name: string;
  /** This API's path to their photo: the day's, else the bar slot's (a trader on the bar with no trade). */
  face: string | null;
  /** Their bar as the feed last confirmed it; null on a past day or off the bar. */
  slot: FollowedBarSlot | null;
  /** Their trades that day; null when they made none. */
  trader: FollowedTrader | null;
}

export function roster(day: FollowedDay, isToday: boolean): RosterEntry[] {
  const traders = new Map(day.traders.map((t) => [t.name, t]));
  const bar = isToday ? day.capture?.bar ?? [] : [];
  const out: RosterEntry[] = bar.map((slot) => {
    const trader = traders.get(slot.trader) ?? null;
    return { name: slot.trader, face: trader?.face ?? slot.face ?? null, slot, trader };
  });
  const shown = new Set(out.map((e) => e.name));
  for (const t of day.traders) {
    if (!shown.has(t.name)) out.push({ name: t.name, face: t.face, slot: null, trader: t });
  }
  return out;
}

export interface StandIn {
  path: string;
  ts: number;
}

/** The trader's newest evidence image of the day and when it was taken: their slot when the feed sends no live one. */
export function newestEvidence(trader: FollowedTrader | null): StandIn | null {
  if (!trader) return null;
  let best: StandIn | null = null;
  for (const t of [...trader.open, ...trader.closed]) {
    const shots: [string | null, number | null][] = [[t.evidence.entry, t.entry.ts], [t.evidence.exit, t.exit?.to_ts ?? null]];
    for (const [path, ts] of shots) {
      if (path && ts !== null && (!best || ts > best.ts)) best = { path, ts };
    }
  }
  return best;
}
