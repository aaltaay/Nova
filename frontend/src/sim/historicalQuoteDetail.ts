/**
 * Quote head during historical replay: the live Stock Quote components read a
 * TickerDetail, so overlay the replay snapshot onto it. Nothing from the live
 * quote (today's price, RVOL, halt, shortability, float, short interest, market cap)
 * may leak into a past session (#881).
 *
 * The card's Gap% is the session's: the regular open (`session_open`) against
 * the prior close -- never the downloaded window's first print, which made a
 * 13:00 window's gap +223% against the real +156% (QA W7). Vol / High / Low
 * are shown only when they are the day's so far (`stats_scope: "session"`);
 * a window that starts after the session start leaves them "--", a stated
 * absence rather than the window's figures passed off as the day's.
 */
import type { AssetInfo, FundamentalsData, TickerDetail } from '../types/ticker';
import { simReplayFactsNote } from './simConstants';
import type { SimClockState } from './simClockTypes';
import type { HistoricalSnapshot } from './useHistoricalSnapshot';

const SPLIT_DATE = /\((\d{4}-\d{2}-\d{2})\)/;
const ISO_DATE = /^(\d{4}-\d{2}-\d{2})/;

/** The split's date in `recent_split` ("1:50 (2026-08-24)"), or null when it names none. */
export function splitDate(recentSplit: string | null | undefined): string | null {
  return SPLIT_DATE.exec(recentSplit ?? '')?.[1] ?? null;
}

/** Extract YYYY-MM-DD from an ISO date or timestamp string, else null. */
export function sessionDateFromStamp(stamp: string | null | undefined): string | null {
  return ISO_DATE.exec(stamp?.trim() ?? '')?.[1] ?? null;
}

/**
 * Static issuer identity fields on `asset` that may survive a replay (#881).
 * Volatile broker flags (`shortable`, `easy_to_borrow`, `tradable`, `marginable`,
 * `status`, margin requirements, `attributes`) describe today and are stripped.
 */
export function replayAssetInfo(asset: AssetInfo | null | undefined): AssetInfo {
  if (!asset) return {};
  const out: AssetInfo = {};
  if (asset.name !== undefined) out.name = asset.name;
  if (asset.exchange !== undefined) out.exchange = asset.exchange;
  if (asset.asset_class !== undefined) out.asset_class = asset.asset_class;
  return out;
}

/**
 * The company facts a past session can show (#881): who the company is (`country`,
 * `country_code`, `sector`, `industry`), a split on or before `sessionDate`, and any
 * historical figures explicitly supplied by a replay source for that day (`recorded`).
 * Never keeps today's Yahoo float/short-interest/market-cap, and never infers a
 * historical float by reversing today's split.
 */
export function replayCompanyFacts(
  f: FundamentalsData | null | undefined,
  sessionDate?: string | null,
  recorded?: Partial<FundamentalsData> | null,
): FundamentalsData | null {
  if (!f && !recorded) return null;
  const split = splitDate(f?.recent_split);
  const keptSplit =
    recorded?.recent_split !== undefined
      ? recorded.recent_split
      : split != null && sessionDate != null && split <= sessionDate
        ? (f?.recent_split ?? null)
        : null;
  return {
    country: recorded?.country ?? f?.country ?? null,
    country_code: recorded?.country_code ?? f?.country_code ?? null,
    sector: recorded?.sector ?? f?.sector ?? null,
    industry: recorded?.industry ?? f?.industry ?? null,
    recent_split: keptSplit,
    market_cap: recorded?.market_cap ?? null,
    shares_outstanding: recorded?.shares_outstanding ?? null,
    float_shares: recorded?.float_shares ?? null,
    held_percent_insiders: recorded?.held_percent_insiders ?? null,
    float_contradicted: recorded?.float_contradicted ?? null,
    float_contradicted_reason: recorded?.float_contradicted_reason ?? null,
    shares_issued: recorded?.shares_issued ?? null,
    shares_issued_reason: recorded?.shares_issued_reason ?? null,
    short_interest: recorded?.short_interest ?? null,
    short_interest_ts: recorded?.short_interest_ts ?? null,
    short_above_float: recorded?.short_above_float ?? null,
    short_above_float_reason: recorded?.short_above_float_reason ?? null,
    short_ratio: recorded?.short_ratio ?? null,
    short_percent_of_float: recorded?.short_percent_of_float ?? null,
    pe_ratio: recorded?.pe_ratio ?? null,
    forward_pe: recorded?.forward_pe ?? null,
    eps: recorded?.eps ?? null,
    fifty_two_week_high: recorded?.fifty_two_week_high ?? null,
    fifty_two_week_low: recorded?.fifty_two_week_low ?? null,
    dividend_yield: recorded?.dividend_yield ?? null,
    beta: recorded?.beta ?? null,
    earnings_date: recorded?.earnings_date ?? null,
  };
}

/**
 * Why volatile company facts (float, short interest, market cap, broker flags) are omitted
 * on a replay of `sessionDate`, naming a post-replay split when `detail` carries one.
 */
export function replayFactsNoteForDetail(
  detail: TickerDetail | null | undefined,
  symbol: string,
  sessionDate: string | null | undefined,
): string {
  const sym = symbol.trim().toUpperCase();
  const day = sessionDate?.trim() || 'this session';
  const own = detail && detail.symbol.toUpperCase() === sym ? detail : null;
  const split = splitDate(own?.fundamentals?.recent_split);
  const later =
    sessionDate && split != null && split > sessionDate
      ? `${sym} split ${own?.fundamentals?.recent_split}`
      : null;
  return simReplayFactsNote(day, later);
}

export function historicalQuoteDetail(
  detail: TickerDetail | null,
  snap: HistoricalSnapshot,
  sessionDate?: string | null,
  recordedFacts?: Partial<FundamentalsData> | null,
): TickerDetail {
  const own = detail && detail.symbol.toUpperCase() === snap.symbol.toUpperCase() ? detail : null;
  const session = snap.stats_scope === 'session';
  // A Massive window's NBBO at the playhead (ADR 046); an IBKR download has none.
  const quoted = snap.bid != null || snap.ask != null;
  const quoteStamp = snap.quote_ts != null && Number.isFinite(snap.quote_ts)
    ? new Date(snap.quote_ts * 1000).toISOString() : snap.as_of || null;
  const day = sessionDate ?? snap.selection?.date ?? sessionDateFromStamp(snap.as_of);
  return {
    symbol: snap.symbol,
    asset: replayAssetInfo(own?.asset),
    // Today's borrow/shortability state is not this session's.
    listing: null,
    halt: null,
    avg_volume: null,
    rel_volume: null,
    rvol_5min: null,
    volume_in_5min: null,
    news: [],
    fundamentals: replayCompanyFacts(own?.fundamentals ?? null, day, recordedFacts),
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
export function captureQuoteDetail(
  detail: TickerDetail | null,
  clock: SimClockState,
  symbol: string,
  recordedFacts?: Partial<FundamentalsData> | null,
): TickerDetail {
  const day = clock.session_date ?? clock.replay_date ?? null;
  const base = simEmptyQuoteDetail(detail, symbol, day, recordedFacts);
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
 * session and nothing is loaded, so today's price, volume, RVOL, halt, float and
 * shortability must not appear at all. A live $1.74 above charts replaying
 * another day is exactly the incoherence the Sim prompt exists to end.
 */
export function simEmptyQuoteDetail(
  detail: TickerDetail | null,
  symbol: string,
  sessionDate?: string | null,
  recordedFacts?: Partial<FundamentalsData> | null,
): TickerDetail {
  const wanted = symbol.trim().toUpperCase();
  const own = detail && detail.symbol.toUpperCase() === wanted ? detail : null;
  return {
    symbol: wanted,
    asset: replayAssetInfo(own?.asset),
    listing: null,
    halt: null,
    avg_volume: null,
    rel_volume: null,
    rvol_5min: null,
    volume_in_5min: null,
    news: [],
    fundamentals: replayCompanyFacts(own?.fundamentals ?? null, sessionDate, recordedFacts),
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
