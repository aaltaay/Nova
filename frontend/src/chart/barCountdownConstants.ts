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

export const CHART_BAR_COUNTDOWN_PAD_X_PX = 5;
export const CHART_BAR_COUNTDOWN_HEIGHT_PX = 16;
export const CHART_BAR_COUNTDOWN_RADIUS_PX = 3;
/** Space between the chip and the candle's wick. */
export const CHART_BAR_COUNTDOWN_GAP_PX = 6;
/** The chip never touches the pane's edges. */
export const CHART_BAR_COUNTDOWN_EDGE_PX = 2;
