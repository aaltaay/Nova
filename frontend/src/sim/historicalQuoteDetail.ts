/**
 * Quote head during historical replay: the live Stock Quote components read a
 * TickerDetail, so overlay the replay snapshot onto it. Nothing from the live
 * quote (today's price, RVOL, halt, shortability) may leak into a past session.
 *
 * The card's Gap% is the session's: the regular open (`session_open`) against
 * the prior close -- never the downloaded window's first print, which made a
 * 13:00 window's gap +223% against the real +156% (QA W7). Vol / High / Low
 * are shown only when they are the day's so far (`stats_scope: "session"`);
 * a window that starts after the session start leaves them "--", a stated
 * absence rather than the window's figures passed off as the day's.
 */
import type { SimClockState } from './simClockTypes';
import type { TickerDetail } from '../types/ticker';
import type { HistoricalSnapshot } from './useHistoricalSnapshot';

export function historicalQuoteDetail(
  detail: TickerDetail | null,
  snap: HistoricalSnapshot,
): TickerDetail {
  const own = detail && detail.symbol.toUpperCase() === snap.symbol.toUpperCase() ? detail : null;
  const session = snap.stats_scope === 'session';
  // A Massive window's NBBO at the playhead (ADR 046); an IBKR download has none.
  const quoted = snap.bid != null || snap.ask != null;
  const quoteStamp = snap.quote_ts != null && Number.isFinite(snap.quote_ts)
    ? new Date(snap.quote_ts * 1000).toISOString() : snap.as_of || null;
  return {
    symbol: snap.symbol,
    asset: own?.asset ?? {},
    // Today's borrow/shortability state is not this session's.
    listing: null,
    halt: null,
    avg_volume: null,
    rel_volume: null,
    rvol_5min: null,
    volume_in_5min: null,
    news: [],
    // Float and sector are not session prices; keep them when they are this ticker's.
    fundamentals: own?.fundamentals ?? null,
    mode: null,
    snapshot: {
      latest_trade: snap.last == null ? null : {
        price: snap.last, size: null, exchange: null, timestamp: snap.as_of || null,
      },
      latest_quote: quoted
        ? {
            bid_price: snap.bid ?? null, bid_size: snap.bid_size ?? null,
            ask_price: snap.ask ?? null, ask_size: snap.ask_size ?? null, timestamp: quoteStamp,
          }
        : null,
      minute_bar: null,
      daily_bar: {
        open: snap.session_open ?? null,
        high: session ? snap.high ?? null : null,
        low: session ? snap.low ?? null : null,
        close: snap.last,
        volume: session ? snap.volume : null,
        trade_count: null,
        vwap: null,
        timestamp: snap.as_of || null,
      },
      prev_daily_bar: null,
      prev_close: snap.prev_close ?? null,
      session_close: null,
      session_prev_close: null,
    },
  };
}

/**
 * Quote head on a Session Record (capture) replay of this symbol (QA W8).
 *
 * The price line already follows the recording's `replay_quote`; the stats row
 * read the live ticker instead -- today's premarket "Vol 3.5M" beside a Sep 21
 * replay, and the same inside a recording gap. A recording holds the stretch
 * the recorder was up: it knows the prior close and the market at the
 * playhead, never the session's volume, high, low or open, so those are a
 * stated absence ("--"), and in a gap so is the price.
 */
export function captureQuoteDetail(detail: TickerDetail | null, clock: SimClockState, symbol: string): TickerDetail {
  const base = simEmptyQuoteDetail(detail, symbol);
  const quote = clock.replay_quote ?? null;
  const stamp = quote?.ts != null && Number.isFinite(quote.ts) ? new Date(quote.ts * 1000).toISOString() : null;
  const covered = quote?.covered === true;
  return {
    ...base,
    snapshot: {
      ...base.snapshot,
      latest_trade: covered && quote?.last != null
        ? { price: quote.last, size: null, exchange: null, timestamp: stamp }
        : null,
      latest_quote: covered && (quote?.bid != null || quote?.ask != null)
        ? {
            bid_price: quote?.bid ?? null, bid_size: quote?.bid_size ?? null,
            ask_price: quote?.ask ?? null, ask_size: quote?.ask_size ?? null, timestamp: stamp,
          }
        : null,
      prev_close: quote?.prev_close ?? null,
    },
  };
}

/**
 * Quote head on a Sim tab with no replay for this symbol.
 *
 * Same rule as above with nothing to put in its place: the desk is a past
 * session and nothing is loaded, so today's price, volume, RVOL, halt and
 * shortability must not appear at all. A live $1.74 above charts replaying
 * another day is exactly the incoherence the Sim prompt exists to end.
 */
export function simEmptyQuoteDetail(detail: TickerDetail | null, symbol: string): TickerDetail {
  const wanted = symbol.trim().toUpperCase();
  const own = detail && detail.symbol.toUpperCase() === wanted ? detail : null;
  return {
    symbol: wanted,
    asset: own?.asset ?? {},
    listing: null,
    halt: null,
    avg_volume: null,
    rel_volume: null,
    rvol_5min: null,
    volume_in_5min: null,
    news: [],
    // Float and sector are not session prices; keep them when they are this ticker's.
    fundamentals: own?.fundamentals ?? null,
    mode: null,
    snapshot: {
      latest_trade: null,
      latest_quote: null,
      minute_bar: null,
      daily_bar: null,
      prev_daily_bar: null,
      prev_close: null,
      session_close: null,
      session_prev_close: null,
    },
  };
}
