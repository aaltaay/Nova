/**
 * Quote head during historical replay: the live Stock Quote components read a
 * TickerDetail, so overlay the replay snapshot onto it. Nothing from the live
 * quote (today's price, RVOL, halt, shortability) may leak into a past session.
 */
import type { TickerDetail } from '../types/ticker';
import type { HistoricalSnapshot } from './useHistoricalSnapshot';

export function historicalQuoteDetail(
  detail: TickerDetail,
  snap: HistoricalSnapshot,
): TickerDetail {
  const matches = detail.symbol.toUpperCase() === snap.symbol.toUpperCase();
  return {
    symbol: snap.symbol,
    asset: matches ? detail.asset : {},
    // Today's borrow/shortability state is not this session's.
    listing: null,
    halt: null,
    avg_volume: null,
    rel_volume: null,
    rvol_5min: null,
    volume_in_5min: null,
    news: [],
    // Float and sector are not session prices; keep them when they are this ticker's.
    fundamentals: matches ? detail.fundamentals : null,
    mode: null,
    snapshot: {
      latest_trade: snap.last == null ? null : {
        price: snap.last, size: null, exchange: null, timestamp: snap.as_of || null,
      },
      latest_quote: null,
      minute_bar: null,
      daily_bar: {
        open: snap.open ?? null,
        high: snap.high ?? null,
        low: snap.low ?? null,
        close: snap.last,
        volume: snap.volume,
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
