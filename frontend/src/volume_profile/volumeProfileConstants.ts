/**
 * Volume profile on the 5-minute chart (ADR 058): every number and word it draws. `VP_ROWS`, `VP_MIN_ROW` and
 * `VP_VALUE_AREA_PCT` mirror `backend/constants_volume_profile.py`.
 */

/** The only pane that draws a profile (decision D4). */
export const VP_TIMEFRAME = '5Min';
/** Histogram rows over the profile's price range (the video's 400, not the platforms' default 24). */
export const VP_ROWS = 400;
/** A row is never thinner than one cent. */
export const VP_MIN_ROW = 0.01;
/** The value area holds this share of the profile's volume. */
export const VP_VALUE_AREA_PCT = 70;

/** Today's profile measures from the 09:30 open unless the operator drags its anchor (decision D7). */
export const VP_DEFAULT_ANCHOR_MIN_ET = 9 * 60 + 30;
/** Yesterday's profile is its regular session. */
export const VP_RTH_START_MIN_ET = 9 * 60 + 30;
export const VP_RTH_END_MIN_ET = 16 * 60;

/** Today's histogram lane right of the last candle, and yesterday's after its 16:00 close (px). */
export const VP_LANE_MAX_PX = 200;
export const VP_LANE_SHARE = 0.2;
export const VP_YESTERDAY_LANE_MAX_PX = 150;
/** Room between the last candle and today's lane (px). */
export const VP_LANE_GAP_PX = 14;
/** Narrower than this right of the last candle (the operator zoomed or panned), today's histogram lies faintly over
 * the candles instead of squeezing to nothing; Nova never moves a view the operator took. */
export const VP_LANE_MIN_PX = 70;
export const VP_OVERLAY_ALPHA_SCALE = 0.5;
/** The pane's tag column at the axis (EMA, VWAP words, `chart/edgeWords.ts`): today's lane ends left of it, so no
 * word sits over the profile. Its width is estimated from the longest word. */
export const VP_EDGE_CHAR_PX = 6.2;
export const VP_EDGE_PAD_PX = 20;
export const VP_EDGE_RESERVE_MAX_PX = 120;
/** Rows averaged on each side for the outline that traces the histogram's shape. */
export const VP_OUTLINE_SMOOTH_ROWS = 3;
/** How near the anchor handle a press must land to grab it (px). */
export const VP_HANDLE_HIT_PX = 8;
/** While the backend is still reading a profile's bars (`filling`), the desk asks again this often. */
export const VP_RETRY_MS = 20_000;
/** Today's profile is read again this often, so each closed 1-minute bar reaches it within a minute. */
export const VP_TODAY_REFRESH_MS = 60_000;

export const VP_COLORS = {
  up: '#0a84ff',
  down: '#ffd60a',
  poc: '#ff453a',
  value: '#0a84ff',
  todayFrame: 'rgba(10, 132, 255, 0.55)',
  todayTint: 'rgba(10, 132, 255, 0.045)',
  todayValueBand: 'rgba(10, 132, 255, 0.085)',
  yesterday: '#8e8e93',
  yesterdayFrame: 'rgba(142, 142, 147, 0.45)',
  yesterdayTint: 'rgba(142, 142, 147, 0.04)',
  yesterdayValueBand: 'rgba(142, 142, 147, 0.08)',
  outline: 'rgba(255, 255, 255, 0.72)',
  label: '#ffffff',
  labelBacking: 'rgba(22, 25, 33, 0.82)',
} as const;

/** Alpha of a histogram row inside and outside the value area. */
export const VP_ROW_ALPHA_IN = 0.82;
export const VP_ROW_ALPHA_OUT = 0.38;
export const VP_YESTERDAY_ALPHA_IN = 0.5;
export const VP_YESTERDAY_ALPHA_OUT = 0.22;

export const VP_LABEL_FONT = '600 10px Inter, "Segoe UI", system-ui, sans-serif';
export const VP_TAG_FONT = '600 9px Inter, "Segoe UI", system-ui, sans-serif';

export const VP_TOGGLE_LABEL = 'Profile';
export const VP_TOGGLE_TITLE =
  'Volume profile on the 5-minute chart: volume traded at each price since the anchor (blue box) and '
  + "yesterday's regular session (grey box). Drag the anchor at the bottom to measure from another candle. Watch only.";
export const VP_PREFS_KEY = 'nova.volumeProfile.shown.v1';

export const vpMissingNote = (which: string, why: string) => `${which} profile: ${why}`;
export const vpTodayTitle = (anchor: string) => `TODAY'S PROFILE  ${anchor} → now`;
export const VP_YESTERDAY_TITLE = "YESTERDAY'S PROFILE  09:30 → 16:00";
export const vpAnchorLabel = (anchor: string) => `⇔  Anchor ${anchor}`;
