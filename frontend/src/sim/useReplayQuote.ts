/**
 * What a Sim tab's price is right now, for the quote head and the ticket
 * (QA 2026-09-22, R10 / V24).
 *
 * Off the live edge a Sim tab trades the loaded replay, so its price is the
 * replay's at the playhead: a capture's from the clock poll (`replay_quote`,
 * which follows every seek), a historical window's from its snapshot. The
 * ticker stream's `latest_trade` is not re-seeded on a seek -- it froze the
 * head (and the ticket's Cost / BP after) at the price the tab opened on. With
 * nothing loaded for this tab, or in a gap in the recording, there is no price
 * and the reason says why; the live feed is never passed off as the replay.
 */
import {
  SIM_REPLAY_PRICE_NONE,
  SIM_REPLAY_PRICE_NOT_DOWNLOADED,
  SIM_REPLAY_PRICE_NOT_RECORDED,
} from './simConstants';
import type { SimClockState } from './simClockTypes';
import type { HistoricalSnapshot } from './useHistoricalSnapshot';
import { useHistoricalSnapshot } from './useHistoricalSnapshot';
import { useSimReplayTarget } from './useSimReplayTarget';

export interface ReplayQuote {
  /** The tab trades a replay (Sim, off the live edge): read these, not the live feed. */
  active: boolean;
  last: number | null;
  bid: number | null;
  ask: number | null;
  /** The replayed session's previous close, when stored. */
  prevClose: number | null;
  /** Why there is no price, when there is none. */
  note: string | null;
}

const INACTIVE: ReplayQuote = { active: false, last: null, bid: null, ask: null, prevClose: null, note: null };
const NONE: ReplayQuote = { active: true, last: null, bid: null, ask: null, prevClose: null, note: SIM_REPLAY_PRICE_NONE };

export function replayQuoteFor(
  symbol: string,
  clock: SimClockState | null | undefined,
  snapshot: HistoricalSnapshot | null | undefined,
  sim: boolean,
): ReplayQuote {
  if (!sim) return INACTIVE;
  // No clock yet: unknown, never the live price.
  if (!clock) return NONE;
  if (clock.live_edge) return INACTIVE;
  const tab = symbol.trim().toUpperCase();
  const replaySymbol = (clock.replay_symbol ?? '').trim().toUpperCase();
  if (clock.replay_source === 'capture' && replaySymbol === tab) {
    const quote = clock.replay_quote;
    if (!quote) return NONE;
    if (!quote.covered) return { ...NONE, prevClose: quote.prev_close, note: SIM_REPLAY_PRICE_NOT_RECORDED };
    return {
      active: true, last: quote.last, bid: quote.bid, ask: quote.ask, prevClose: quote.prev_close,
      note: quote.last == null ? SIM_REPLAY_PRICE_NONE : null,
    };
  }
  if (clock.replay_source === 'historical' && replaySymbol === tab && snapshot?.active) {
    // A download's uncovered stretch was not downloaded -- not a recording gap (W25);
    // the backend refuses practice orders there too (R34).
    if (snapshot.covered === false && snapshot.source !== 'completed_bars') {
      return { ...NONE, prevClose: snapshot.prev_close ?? null, note: SIM_REPLAY_PRICE_NOT_DOWNLOADED };
    }
    return {
      active: true, last: snapshot.last, bid: null, ask: null, prevClose: snapshot.prev_close ?? null,
      note: snapshot.last == null ? SIM_REPLAY_PRICE_NONE : null,
    };
  }
  return NONE;
}

export function useReplayQuote(symbol: string): ReplayQuote {
  const { sim, clock } = useSimReplayTarget(symbol);
  const historical = useHistoricalSnapshot(symbol, sim && clock?.replay_source === 'historical');
  return replayQuoteFor(symbol, clock, historical, sim);
}

/** What a ticket prices from: the price, why there is none, and the quote a Market order fills against. */
export interface VenuePrice {
  price: number | null;
  note: string | null;
  bid: number | null;
  ask: number | null;
}

/**
 * The replay's price and quote off the live edge (with why it has none), else
 * the live last and the live top of book (`liveBook`, this symbol's only).
 */
export function venuePriceFor(
  replay: ReplayQuote,
  livePrice: number | null,
  liveBook: { bid: number | null; ask: number | null } | null = null,
): VenuePrice {
  return replay.active
    ? { price: replay.last, note: replay.note, bid: replay.bid, ask: replay.ask }
    : { price: livePrice, note: null, bid: liveBook?.bid ?? null, ask: liveBook?.ask ?? null };
}

/**
 * Where a Market order fills: the far side of a known quote -- the ask to buy,
 * the bid to sell -- exactly as the practice broker fills it
 * (architecture/practice-fills.md). Null without one; the ticket then prices
 * from the last. The Cost line used the last while the fill took the ask (QA R36).
 */
export function marketFillPrice(side: 'BUY' | 'SELL', venue: Pick<VenuePrice, 'bid' | 'ask'>): number | null {
  const px = side === 'BUY' ? venue.ask : venue.bid;
  return px != null && Number.isFinite(px) && px > 0 ? px : null;
}

export function useVenuePrice(
  symbol: string,
  livePrice: number | null,
  liveBook: { bid: number | null; ask: number | null } | null = null,
): VenuePrice {
  return venuePriceFor(useReplayQuote(symbol), livePrice, liveBook);
}
