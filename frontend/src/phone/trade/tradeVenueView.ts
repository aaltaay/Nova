/**
 * What the Trade screen draws on each venue (ADR 070 amendment 2026-11-13). Pure, so it is tested without a
 * screen. Every rule here is the desk's (`sim/simReplayTarget`, the Trader's Sim rail): the phone adds only
 * what it cannot draw yet -- a replay from the Massive files -- and says so instead of drawing something else.
 *
 * - Paper: the live book, tape and quote; the ticket trades.
 * - Live: the same live screen to look at; the ticket sends nothing from the phone.
 * - Sim at the live edge: live, as Paper (the desk's live-edge rule); the ticket trades the Sim.
 * - Sim replaying a Session Record of this stock: the same sockets serve the recording, the quote is the
 *   recording's at the playhead, and a gap in the recording is said as a gap.
 * - Sim with anything else: the desk's own words in place of the book and the tape, and a ticket that sends
 *   nothing, never today's live panes over a past session.
 */
import { simRailNote, simReplayTarget, type SimClockState } from '../../sim';
import type { Venue } from '../PhoneSession';

export const LIVE_LOOK_ONLY = 'From the phone, Live is look only. Send Live orders from the PC.';
/** The desk's own words for a gap in a Session Record (the Trader's capture-gap watch). */
export const CAPTURE_GAP = 'The playhead is between recorded stretches: nothing was recorded here.';

export function massiveNote(symbol: string): string {
  return `The desk is replaying ${symbol} from the Massive files. The phone does not draw that replay yet: watch it on the PC. Nothing is sent from here.`;
}

export interface TradeVenueView {
  /** The book and tape remount across it, so they reopen the real line at the live edge and the replay off it. */
  feedKey: 'live' | 'live-edge' | 'replay';
  /** Whose quote the header shows: today's, the recording's at the playhead, or none. */
  quote: 'live' | 'capture' | 'empty';
  /** Words in place of the book and the tape; null draws them. */
  note: string | null;
  /** The Session Record has a gap at the playhead. */
  gap: boolean;
  /** Why the ticket sends nothing, and the short word on its buttons; null when it trades. */
  blocked: { why: string; word: string } | null;
}

const LIVE: TradeVenueView = { feedKey: 'live', quote: 'live', note: null, gap: false, blocked: null };

export function tradeVenueView(symbol: string, venue: Venue | null, clock: SimClockState | null, sim: boolean): TradeVenueView {
  if (venue === 'live') return { ...LIVE, blocked: { why: LIVE_LOOK_ONLY, word: 'Live · look only' } };
  if (!sim) return LIVE;
  if (clock?.live_edge === true) return { ...LIVE, feedKey: 'live-edge' };
  const target = simReplayTarget(symbol, clock, sim);
  if (target.kind === 'ok' && clock?.replay_source === 'historical') {
    const why = massiveNote(symbol);
    return { feedKey: 'replay', quote: 'empty', note: why, gap: false, blocked: { why, word: 'Sim · on the PC' } };
  }
  const note = simRailNote(symbol, clock, sim);
  if (note) return { feedKey: 'replay', quote: 'empty', note, gap: false, blocked: { why: note, word: 'Sim · nothing here' } };
  return { feedKey: 'replay', quote: 'capture', note: null, gap: clock?.replay_quote?.covered === false, blocked: null };
}
