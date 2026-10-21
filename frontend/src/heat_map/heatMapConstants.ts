/** The heat map's numbers and words (ADR 061). Mockup: F:/Nova/design/heatmap/v3 (operator-approved 2026-10-20). */

// ── What the desk keeps ────────────────────────────────────────────────────────────────────────────
/** Book and tape kept per stock, in market seconds: the widest window. */
export const HEAT_KEEP_SEC = 1800;
/** At most one book snapshot per slot (the newest in the slot wins): 10 a second. */
export const HEAT_BOOK_SLOT_SEC = 0.1;
/** Stocks kept at once: IBKR's 3 Level 2 lines plus one for a switch. The least recently fed goes first. */
export const HEAT_MAX_SYMBOLS = 4;
/** A print this many market seconds behind the newest means a replay went back: that stock starts over. */
export const HEAT_REWIND_SEC = 2;
/** Prints this far (seconds) from the browser clock mean a replay's clock: beats (browser time) never move it. */
export const HEAT_REPLAY_OFFSET_SEC = 60;
/** The last book stays drawn while the line keeps beating, plus this grace; after it the screen goes black. */
export const HEAT_ALIVE_GRACE_SEC = 2;
/** A book wider than this many ticks is cut to this many either side of its middle (a bad row cannot blow memory). */
export const HEAT_MAX_HALF_TICKS = 500;
/** Prices under $1 are binned at a tenth of a cent; $1 and over at a cent. */
export const HEAT_TICK_DOLLAR = 0.01;
export const HEAT_TICK_SUB_DOLLAR = 0.001;

// ── Trades as dots: bursts, not clock slices (operator, 2026-10-20) ────────────────────────────────
/** A burst of buying (at the ask) ends when a seller hits the bid, after this pause, or this many ticks from its start. */
export const HEAT_BURST_GAP_SEC = 1;
export const HEAT_BURST_MOVE_TICKS = 2;
/** Bursts smaller than the chosen size get no dot; they still count in the volume bars. */
export const HEAT_DOT_MIN_OPTIONS = [500, 1000, 2000, 5000] as const;
export const HEAT_DOT_MIN_DEFAULT = 1000;
/** Dot radius (CSS px): the window's biggest burst gets the max, area in proportion. */
export const HEAT_DOT_R_MAX = 20;
export const HEAT_DOT_R_MIN = 2.2;
/** In-between prints have no aggressor: their dots are fainter. */
export const HEAT_DOT_MID_ALPHA = 0.45;

// ── The window across the screen: no candles, the trader picks how much time fits ──────────────────
export const HEAT_WINDOWS_SEC = [60, 300, 900, 1800] as const;
export const HEAT_WINDOW_DEFAULT_SEC = 300;
export const HEAT_WINDOW_MIN_SEC = 30;
export const HEAT_WINDOW_MAX_SEC = HEAT_KEEP_SEC;
/** One mouse-wheel notch zooms by this factor. */
export const HEAT_WHEEL_STEP = 1.2;

// ── Colour: log10(shares) from the floor (dimmest) to the brightness's cap (red) ───────────────────
export const HEAT_FLOOR_SHARES = 150;
export const HEAT_BRIGHTNESS_DEFAULT = 45;
/** log10 of the shares that read red at brightness 0 and at 100 (45 reads red near 37,000 shares). */
export const HEAT_CAP_LOG_DIM = 5.2;
export const HEAT_CAP_LOG_BRIGHT = 3.8;
/** Few shares -> many: navy, blue, cyan, white, yellow, orange, red (the Bookmap / thinkorswim scale). */
export const HEAT_RAMP: ReadonlyArray<readonly [number, string]> = [
  [0.0, '#08204a'], [0.25, '#0f3f8f'], [0.42, '#1565c0'], [0.55, '#29b6f6'],
  [0.66, '#e0f7ff'], [0.76, '#ffe24a'], [0.87, '#ff9100'], [1.0, '#e8231c'],
];
/** Inside the rows IBKR sent with nothing waiting, and past them (never seen, never drawn as empty). */
export const HEAT_BG_SEEN: readonly [number, number, number] = [5, 10, 22];
export const HEAT_BG_UNSEEN: readonly [number, number, number] = [0, 0, 0];
/** Each price is a line: full strength within this share of a tick of its middle, then a soft edge. */
export const HEAT_LINE_CORE = 0.16;
export const HEAT_LINE_SOFT = 0.09;
/** Sub-rows per tick that draw the line's profile; below this many pixels a tick the rows touch instead. */
export const HEAT_SUBROWS = 8;
export const HEAT_GAP_MIN_PX = 6;
/** Below this, a small order still shows a little; above it the line is at full strength. */
export const HEAT_DIM_LEVEL = 0.5;

// ── Layout (CSS px) and drawing ───────────────────────────────────────────────────────────────────
export const HEAT_AXIS_W = 64;
export const HEAT_BOOK_W = 176;
export const HEAT_VOLUME_H = 64;
export const HEAT_TIME_H = 24;
export const HEAT_GAP = 8;
export const HEAT_VOLUME_BARS = 60;
/** Price padding around the window's best bid / ask, in ticks, and the least ticks a screen shows. */
export const HEAT_PAD_TICKS = 3;
export const HEAT_MIN_SPAN_TICKS = 20;
/** The most ticks one screen shows; a wider window is cut around the newest middle (no giant grid). */
export const HEAT_MAX_SPAN_TICKS = 1200;
/** At most one redraw per this many ms: the order path never waits on a picture (ADR 045). */
export const HEAT_FRAME_MS = 150;
/** CSS pixels per time column of the book grid: half the pixels to fill, still a fraction of a second each. */
export const HEAT_COL_PX = 2;
/** The device-pixel ratio the canvas draws at, at most (a 4K desk at 150% stays cheap). */
export const HEAT_MAX_DPR = 2;
export const HEAT_FONT = '12px Inter, "Segoe UI", system-ui, sans-serif';
export const HEAT_FONT_BOLD = '600 12px Inter, "Segoe UI", system-ui, sans-serif';
export const HEAT_TEXT = '#e6e8ee';
export const HEAT_MUTED = '#9aa3b5';
export const HEAT_DIM = '#5d6475';
export const HEAT_GREEN = '#22c55e';
export const HEAT_RED = '#ef4444';
export const HEAT_GREY = '#6b7280';
export const HEAT_MID_LINE = 'rgba(230, 235, 242, 0.6)';
export const HEAT_MINUTE_LINE = 'rgba(255, 255, 255, 0.28)';
/** Sphere colours per side (bought at the ask, sold at the bid, between): highlight, body, rim. */
export const HEAT_SPHERES: ReadonlyArray<readonly [string, string, string]> = [
  ['#eafff1', '#2fd872', '#0b5e2c'],
  ['#fff1f1', '#ff5252', '#7a0c0c'],
  ['#f7f7f8', '#a3a9b4', '#454a53'],
];
export const HEAT_ET_ZONE = 'America/New_York';

// ── Saved choices ─────────────────────────────────────────────────────────────────────────────────
export const HEAT_PREFS_KEY = 'nova.heatMap.prefs.v1';
export const HEAT_PREFS_VERSION = 1;

// ── Words ─────────────────────────────────────────────────────────────────────────────────────────
export const HEAT_TOGGLE_LABEL = 'Heat map';
export const HEAT_TOGGLE_TITLE =
  "Swap the four charts for the heat map: Level 2 over time. Each line is a price where shares wait, brighter = more; "
  + 'dots are bursts of trades. Click again for the charts.';
export const HEAT_BACK_TITLE = 'Back to the four charts';
export const HEAT_SCALE_FEW = 'few shares';
export const HEAT_SCALE_MANY = 'many shares';
export const HEAT_LEGEND_ASK = 'bought at the ask';
export const HEAT_LEGEND_BID = 'sold at the bid';
export const HEAT_LEGEND_MID = 'between or unknown';
export const HEAT_DOTS_TITLE = 'Smallest burst that gets a dot (smaller trades still count in the volume bars). Click for the next size.';
export const HEAT_BRIGHTNESS_LABEL = 'Brightness';
export const HEAT_BRIGHTNESS_TITLE = 'How many shares read as red: brighter shows smaller orders hotter.';
export const HEAT_BOOK_NOW = 'Book now';
export const HEAT_VOLUME = 'Volume';
export const HEAT_UNSEEN_NOTE = 'Black: past the 10 rows of the book IBKR sends.';
export const heatWindowLabel = (sec: number) => (sec % 60 === 0 ? `${sec / 60} min` : `${Math.round(sec)} s`);
export const heatDotsLabel = (shares: number) => `Dots: ${shares >= 1000 ? `${shares / 1000}k` : shares}+ shares`;
export const heatVolumePer = (sec: number) => `per ${sec < 60 ? `${Math.round(sec)} s` : `${Math.round(sec / 60)} min`}`;
export const heatWaiting = (symbol: string) =>
  `Waiting for ${symbol}'s Level 2. The heat map draws IBKR's book from the moment Nova opens it; IBKR keeps no history.`;
export const heatStale = (clock: string) => `No Level 2 since ${clock}: the screen stays black until the book is back.`;
export const HEAT_L1_ONLY = 'IBKR is sending only the best bid and ask for this stock (no depth), so there are no lines to draw.';
export const heatLineDown = (why: string) => `Level 2 is not live: ${why}`;
export const HEAT_LINE_LENT = "lent to one of Nova's setups; it comes back when this tab is in front.";
