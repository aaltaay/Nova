/** Earnings and split marks on the daily charts (operator ask, 2026-10-12). */

export const CHART_EVENTS_PATH = '/api/chart-events';
/** While the desk is still reading a symbol's filings (a foreign issuer's 6-Ks), it is asked again this often. */
export const CHART_EVENTS_RETRY_MS = 3000;
/** Asks while a read is under way before the pane stops asking; the next symbol or refresh asks again. */
export const CHART_EVENTS_MAX_RETRIES = 60;
/** A read the pane holds is asked for again after this long: a filing that came in, a new day. */
export const CHART_EVENTS_REFRESH_MS = 10 * 60_000;
/** A daily mark sits on the first candle on or after its day, never further than this past it (a halt). */
export const CHART_EVENT_DAILY_SNAP_DAYS = 7;

/** The marks: a ring with a letter, along the bottom of the price pane, a second one on a candle above the first. */
export const CHART_EVENT_RADIUS_PX = 8;
export const CHART_EVENT_RING_PX = 1.5;
export const CHART_EVENT_FONT_PX = 10;
export const CHART_EVENT_BOTTOM_GAP_PX = 6;
export const CHART_EVENT_STACK_GAP_PX = 3;
export const CHART_EVENT_HIT_SLACK_PX = 3;
/** E for earnings; M for a split, as the operator's other platform marks one. */
export const CHART_EVENT_LETTERS = { earnings: 'E', split: 'M' } as const;
export const CHART_EVENT_COLORS = { earnings: '#60a5fa', split: '#a78bfa' } as const;
export const CHART_EVENT_FILL = 'rgba(12, 12, 14, 0.85)';
/** The card's width beside the pointer, and the gap between them. */
export const CHART_EVENT_CARD_W_PX = 280;
export const CHART_EVENT_CARD_GAP_PX = 14;
/** The 6-K sentence quoted on the card is cut at this many characters. */
export const CHART_EVENT_SAID_CHARS = 160;
