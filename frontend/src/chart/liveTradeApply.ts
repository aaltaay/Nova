/**
 * Pure live-trade → candle merge (used by useChartLiveTrade + tests).
 * Forward jumps are allowed for intraday; daily+ only updates the matching tip.
 *
 * The forming candle's volume is counted here too: every live trade update
 * carries the day's running volume, and a bar's volume is what that total
 * grew by while the bar was open. A bar whose start the chart did not see has
 * no live count -- the store's figure, or nothing, never a partial guess.
 */
import type { CandlestickData, Time } from 'lightweight-charts';
import {
  isDailyTimeframe,
  isOutOfOrderTrade,
  tradeBucket,
} from '../tickerChartData';

export function mergeLiveTradeCandle(
  prev: CandlestickData<Time> | null,
  trade: { price: number; timestamp: string; source?: string },
  timeframe: string,
): CandlestickData<Time> | null {
  if (!trade.price || !trade.timestamp) return null;
  // A Level 1 snapshot is a last price, not a print. After the close it can be
  // the regular session's last while the tape trades a dollar away; painting
  // it drew a wick no exchange printed (QA 2026-09-22). Candles take prints only.
  if (trade.source === 'snapshot') return null;
  const bucket = tradeBucket(trade.timestamp, timeframe);
  if (bucket === null) return null;
  if (isOutOfOrderTrade(prev, bucket)) return null;

  const price = trade.price;
  const daily = isDailyTimeframe(timeframe);

  // Do not invent the first candle from a tick -- that zooms the empty
  // pane onto "now" so later setData(history) without fitContent looks empty.
  if (!prev) return null;

  if (prev.time === bucket) {
    return {
      time: bucket,
      open: prev.open,
      high: Math.max(prev.high, price),
      low: Math.min(prev.low, price),
      close: price,
    };
  }

  // Daily+ bars use business-day string times -- never invent a new period from a tick.
  if (daily) return null;

  // Intraday (incl. 10Sec): any forward bucket opens a new tip candle (gap OK).
  return { time: bucket, open: price, high: price, low: price, close: price };
}

/**
 * Whether the chart counts a forming bar's volume from live trade updates.
 * 10Sec bars take their volume from the tape's own prints (`barsStore`), and a
 * daily bar's volume is the store's; everything else in between is counted.
 */
export function countsLiveVolume(timeframe: string): boolean {
  return timeframe !== '10Sec' && !isDailyTimeframe(timeframe);
}

/** Running count of the forming bar's volume from the day's volume total. */
export interface LiveVolumeState {
  /** The last day volume a trade update carried; null before the first. */
  mark: number | null;
  /** The bar `volume` counts. */
  bar: Time | null;
  /** Shares the day volume grew by since `bar` opened; null when not known. */
  volume: number | null;
}

export const EMPTY_LIVE_VOLUME: LiveVolumeState = { mark: null, bar: null, volume: null };

/**
 * Advance the count by one trade update in bar `bar`.
 *
 * The first day volume seen is a baseline, not a count: the bar it lands in
 * opened before the chart was watching, so its volume stays unknown. Every
 * later bar is counted from its first update. A total that goes down (a new
 * day's count, or the line changed its source) restarts the baseline and
 * leaves that bar unknown. An update with no day volume keeps the mark, so
 * the next one's growth still covers it.
 *
 * Updates arrive when the price changes; shares traded at an unchanged price
 * just before a bar closes are counted in the next bar. The store's own bar
 * replaces a closed bar's figure when it lands.
 */
export function stepLiveVolume(
  state: LiveVolumeState,
  bar: Time,
  dayVolume: number | null | undefined,
): LiveVolumeState {
  const newBar = state.bar === null || state.bar !== bar;
  const base = newBar ? (state.mark !== null ? 0 : null) : state.volume;
  const total = typeof dayVolume === 'number' && Number.isFinite(dayVolume) && dayVolume >= 0
    ? dayVolume
    : null;
  if (total === null) return { mark: state.mark, bar, volume: base };
  if (state.mark === null || total < state.mark) return { mark: total, bar, volume: null };
  return {
    mark: total,
    bar,
    volume: base === null ? null : base + (total - state.mark),
  };
}

/** The volume a forming bar shows: the larger of the live count and the store's. */
export function shownTipVolume(
  live: number | null,
  store: number | null,
): number | null {
  if (live === null) return store;
  if (store === null) return live;
  return Math.max(live, store);
}

/** The candle and volume Nova drew from live trades for the forming bar. */
export interface LiveTip {
  candle: CandlestickData<Time>;
  /** The live count for this bar, or null when its start was not seen. */
  volume: number | null;
}

/**
 * Put the live tip back on top of a fresh store paint.
 *
 * A store tip older than the live one keeps the live candle as drawn; one for
 * the same bar merges (the store saw the bar open, the live tip has the latest
 * trade); a newer store tip means the store has moved on and the live tip is
 * dropped (`null`). Rebuilding the tip from the last trade alone used to
 * collapse the forming candle to one price on every refresh.
 */
export function restoreLiveTip(
  store: { candle: CandlestickData<Time>; volume: number | null } | null,
  live: LiveTip | null,
): { candle: CandlestickData<Time>; volume: number | null } | null {
  if (live === null) return null;
  if (store === null) return live;
  if (isOutOfOrderTrade(store.candle, live.candle.time)) return null;
  if (store.candle.time !== live.candle.time) return live;
  return {
    candle: {
      time: live.candle.time,
      open: store.candle.open,
      high: Math.max(store.candle.high, live.candle.high),
      low: Math.min(store.candle.low, live.candle.low),
      close: live.candle.close,
    },
    volume: shownTipVolume(live.volume, store.volume),
  };
}
