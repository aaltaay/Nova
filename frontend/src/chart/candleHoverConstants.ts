/** The candle's hover card (operator ask, 2026-10-12). */

/** How long the pointer rests on one candle before its card opens; a sweep across candles never opens it. */
export const CANDLE_HOVER_DWELL_MS = 1000;
/** Pixels above the high and under the low that still count as "on the candle", so a thin candle is easy to hit. */
export const CANDLE_HOVER_HIT_SLACK_PX = 6;
/** The open card reads its candle again this often, so the forming candle's numbers keep up with the prints. */
export const CANDLE_HOVER_REFRESH_MS = 500;
/** The candle's volume is compared with the average of this many candles before it. */
export const CANDLE_HOVER_VOLUME_LOOKBACK = 20;
/** Bars walked back looking for those candles, past whitespace another series put on the time scale. */
export const CANDLE_HOVER_VOLUME_SCAN_LIMIT = 60;
/** The volume meter's full width, as a multiple of that average. */
export const CANDLE_HOVER_VOLUME_METER_MAX = 4;
/** The card's width, and the gap between it and the pointer. */
export const CANDLE_HOVER_CARD_W_PX = 280;
export const CANDLE_HOVER_CARD_GAP_PX = 16;
/** The card never touches the pane's edges. */
export const CANDLE_HOVER_EDGE_PX = 4;
