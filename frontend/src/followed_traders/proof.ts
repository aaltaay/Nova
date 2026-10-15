/**
 * Checking one trade against what the vision read (the Proof view). The feed logs a change only once the same read
 * holds on consecutive frames, so while the trade was held every read of the slot either showed it at the price the
 * feed logged then, or was a read the feed ignored. Pure.
 */
import { FT_CLOSE_NOT_SEEN, FT_CLOSED_ON_LEAVING, FT_STILL_OPEN } from './constants';
import { gluedRead } from './ticker';
import type { BarPosition, FollowedRead, FollowedTrade } from './types';

export type ReadVerdict = 'entry' | 'held' | 'ignored' | 'not_seen' | 'exit' | 'before' | 'after';

export interface JudgedRead extends FollowedRead {
  verdict: ReadVerdict;
}

/** The price the bar showed for the trade at `ts`: its first price, then each add's from the add on. */
export function expectedPrice(t: FollowedTrade, ts: number): number {
  let p = t.entry.first_price;
  for (const a of t.adds) if (a.ts <= ts) p = a.price;
  return p;
}

/** The read shows the trade at the price the feed logged then: as its ticker, or that ticker glued to its price
 *  (SOFI 14.03 read SOF 114.03), which is the same position read wrong, not one the feed ignored. */
export function holdsTrade(read: FollowedRead, t: FollowedTrade, ts: number): boolean {
  const want = expectedPrice(t, ts);
  const glued = gluedRead(t.symbol, want);
  return read.positions.some((p) => p.side === t.side && ((p.symbol === t.symbol && p.price === want)
    || (glued !== null && p.symbol === glued.symbol && p.price === glued.price)));
}

/** When the trade left the bar (its exit's end), or null while it is open or its close was never seen. */
export function exitTs(t: FollowedTrade): number | null {
  return t.status === 'closed' ? t.exit?.to_ts ?? null : null;
}

export function judgeReads(t: FollowedTrade, reads: FollowedRead[]): { reads: JudgedRead[]; ignored: number } {
  const out = exitTs(t);
  let ignored = 0;
  const judged = reads.map((r): JudgedRead => {
    let verdict: ReadVerdict;
    if (r.ts < t.entry.ts) verdict = 'before';
    else if (out !== null && r.ts >= out) verdict = r.ts === out ? 'exit' : 'after';
    else if (r.ts === t.entry.ts) verdict = 'entry';
    else if (!r.seen) verdict = 'not_seen';
    else if (r.unparsed.length === 0 && holdsTrade(r, t, r.ts)) verdict = 'held';
    else verdict = 'ignored';
    if (verdict === 'ignored') ignored += 1;
    return { ...r, verdict };
  });
  return { reads: judged, ignored };
}

/** The read in force at `ts` (the last that began by then), or null. */
export function readAt(reads: FollowedRead[], ts: number): FollowedRead | null {
  let found: FollowedRead | null = null;
  for (const r of reads) if (r.ts <= ts) found = r;
  return found;
}

export function sideRow(positions: BarPosition[], side: BarPosition['side']): BarPosition[] {
  return positions.filter((p) => p.side === side);
}

/** What stands in for the exit image when there is none: still open, closed when they left the bar, or a close the
 *  feed never saw. */
export function noExitImage(t: FollowedTrade): string {
  if (t.status === 'open') return FT_STILL_OPEN;
  return t.left_bar ? FT_CLOSED_ON_LEAVING : FT_CLOSE_NOT_SEEN;
}
