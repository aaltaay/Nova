/** The forming candle's close countdown (operator ask, 2026-09-24). */

/** Only minute candles count down: 10-second bars roll too fast to read, hours and days too slowly to need it. */
export const CHART_BAR_COUNTDOWN_TIMEFRAME_RE = /^(\d+)Min$/;
/** The last seconds before the close are drawn in the warning colour. */
export const CHART_BAR_COUNTDOWN_WARN_SEC = 10;

export const CHART_BAR_COUNTDOWN_FONT = '600 11px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
export const CHART_BAR_COUNTDOWN_TEXT_COLOR = '#c9cfdb';
export const CHART_BAR_COUNTDOWN_WARN_COLOR = '#f59e0b';
/** The chart background (#161921), nearly opaque, so wicks and grid lines never run through the digits. */
export const CHART_BAR_COUNTDOWN_BACK_COLOR = 'rgba(22, 25, 33, 0.88)';
export const CHART_BAR_COUNTDOWN_BORDER_COLOR = 'rgba(139, 146, 165, 0.45)';
/**
 * The countdown as a label on the price scale (the phone's charts). It reads as one label with the last price
 * (operator, 2026-11-17, mockup A: the grey plate under the price went unseen): the last candle's own colour, the
 * price label's white, and exactly one label's height under it so the two touch. The grey is what it falls back to
 * when the candle's colour cannot be read.
 */
export const CHART_BAR_COUNTDOWN_SCALE_BACK_COLOR = '#2A3140';
export const CHART_BAR_COUNTDOWN_SCALE_TEXT_COLOR = '#FFFFFF';
/** A scale label's height over its type size in lightweight-charts: the type plus 2.5/12 of it above and below. */
export const CHART_BAR_COUNTDOWN_SCALE_LABEL_RATIO = 17 / 12;

export const CHART_BAR_COUNTDOWN_PAD_X_PX = 5;
export const CHART_BAR_COUNTDOWN_HEIGHT_PX = 16;
export const CHART_BAR_COUNTDOWN_RADIUS_PX = 3;
/** Space between the chip and the candle's wick. */
export const CHART_BAR_COUNTDOWN_GAP_PX = 6;
/** The chip never touches the pane's edges. */
export const CHART_BAR_COUNTDOWN_EDGE_PX = 2;
/** Room kept between the chip and any word on the pane (a label, a pin, an edge tag). */
export const CHART_BAR_COUNTDOWN_WORD_GAP_PX = 2;
/** Rows above and under the wick the chip may climb to when words crowd its usual spot. */
export const CHART_BAR_COUNTDOWN_STACK_ROWS = 3;
/** Candle spacing assumed for the spots beside the candle when the pane does not say (lightweight-charts' default). */
export const CHART_BAR_COUNTDOWN_BAR_SPACING_PX = 6;
