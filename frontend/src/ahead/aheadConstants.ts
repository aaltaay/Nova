/**
 * Ahead (ADR 065): every number, colour and sentence the forecast zone uses. A forecast is never data: every word
 * here that carries an AI number says it is the forecaster's view. `AHEAD_HORIZON`, `AHEAD_LEVELS` and the setup
 * families mirror `backend/constants_ahead.py`; the setup names are `backend/constants_setups.py`'s.
 */
import type { AheadScope } from './aheadTypes';

/** The only pane Ahead draws on. */
export const AHEAD_TIMEFRAME = '1Min';
/** One-minute steps in the zone. */
export const AHEAD_HORIZON = 15;
/** Paths drawn on the chart (all `n` are used for the odds and the MACD fan). */
export const AHEAD_DRAWN_PATHS = 16;
/** Switched on (and on each new answer while the view follows the right edge and is Nova's), the 1-minute pane is
 * framed like the approved mockup: this many real candles, the 15-step zone and a small margin after it, plus the
 * stock read's word column at the edge -- the zone takes about a quarter of the pane. */
export const AHEAD_FRAME_CANDLES = 45;
export const AHEAD_FRAME_MARGIN = 2;
/** Real 1-minute volume bars before "now" in the panel's volume chart. */
export const AHEAD_RECENT_VOLUME_BARS = 30;
/** A strategy target within this of a wall is that wall (half a cent). */
export const AHEAD_SAME_PRICE = 0.005;
/** The quantile levels the wire always carries, looked up by value. */
export const AHEAD_LEVELS = [0.1, 0.25, 0.5, 0.75, 0.9] as const;
export const AHEAD_LEVEL_EPS = 1e-9;
/** Consecutive minutes a stock's newest candles need before a meet is told as a clock time (else in candles). */
export const AHEAD_CONTIGUOUS_TAIL = 30;
export const AHEAD_STEP_SEC = 60;
/** Minute labels in the zone fall on multiples of this many minutes. */
export const AHEAD_TICK_EVERY_MIN = 5;

/** The answer's own promise, word for word as the backend sends it. */
export const AHEAD_NEVER = 'A forecast only: nothing here places, blocks, sizes or delays an order.';

export const AHEAD_PREFS_KEY = 'nova.ahead.prefs';
export const AHEAD_SCOPES: readonly AheadScope[] = ['all', 'lines', 'flat_top', 'first_pullback'];

// ---------------------------------------------------------------- asking

/** The poller looks at the clock this often (it asks far less: see below). */
export const AHEAD_BEAT_MS = 500;
/** After the desk minute rolls over, wait this long so the candle that closed is in Nova's store. */
export const AHEAD_MINUTE_SETTLE_MS = 1500;
/** While the backend is reading a minute: ask again after its `retry_ms`, this when it gives none. */
export const AHEAD_PENDING_RETRY_MS = 1000;
/** At most this many quick asks in a row; then the slow cadence. */
export const AHEAD_PENDING_MAX_TRIES = 15;
/** A `ready` answer for the minute before the one that just closed: ask again this many times (Nova's store may not
 * hold the closed candle yet), then wait for the next minute -- a stock with no trade in that minute has no newer
 * candle to forecast from. */
export const AHEAD_STALE_READY_MAX_TRIES = 3;
/** warming / offline / quiet / error / not set up / an API that did not answer: ask again this often. */
export const AHEAD_SLOW_RETRY_MS = 15_000;
/** The status (exam and report card) is read this often while the panel is open. */
export const AHEAD_STATUS_POLL_MS = 30_000;
/** After a scrub, an answer made more than this after the playhead is from before the rewind: dropped. */
export const AHEAD_REWIND_SLACK_SEC = 2;
/** How long after a scrub that check runs (forward play makes the desk's playhead lag the backend's). */
export const AHEAD_SCRUB_FENCE_MS = 10_000;

// ---------------------------------------------------------------- setups and walls

/** Ahead's two strategy scopes and the setup lanes each reads (long side, 1-minute candles). */
export const AHEAD_SETUP_FAMILIES = {
  flat_top: ['flat_top_breakout', 'second_flat_top_breakout'],
  first_pullback: ['first_pullback'],
} as const;
export type AheadFamily = keyof typeof AHEAD_SETUP_FAMILIES;
export const AHEAD_FAMILY_WORD: Record<AheadFamily, string> = { flat_top: 'flat top', first_pullback: 'first pullback' };
/** armed > near > forming (a `leg` / `pullback` lane carrying forming levels). */
export const AHEAD_LANE_RANK = { armed: 3, near: 2, forming: 1 } as const;
export const AHEAD_FORMING_STATES: readonly string[] = ['leg', 'pullback'];
/** A level zone whose every reason is one of these is not a wall (a round number or VWAP moves or means little). */
export const AHEAD_NOT_A_WALL: readonly string[] = ['whole', 'half', 'vwap'];

// ---------------------------------------------------------------- colours

export const AHEAD_COLORS = {
  ai: '#93a4d6',
  path: '#c7d2fe',
  hatch: '#1b2030',
  hatchStripe: 'rgba(255, 255, 255, 0.045)',
  /** Nova's own lines: the same as the stock read's trend lines (`stock_read/constants.ts` TREND_COLORS). */
  support: '#34d399',
  resistance: '#ff9f43',
  meetRing: '#e6e8ee',
  wallAbove: '#f0876f',
  wallBelow: '#2dd4bf',
  trigger: '#5eb1ff',
  stop: '#fca5a5',
  target: '#86efac',
  muted: '#8b92a5',
  text: '#e6e8ee',
  chipBg: 'rgba(11, 13, 18, 0.9)',
  heading: '#c7d2fe',
  aiTagFg: '#c7d2fe',
  aiTagBg: 'rgba(147, 164, 214, 0.16)',
  notPassedFg: '#ffb340',
  notPassedBg: 'rgba(255, 159, 10, 0.18)',
  passedFg: '#30d158',
  passedBg: 'rgba(48, 209, 88, 0.14)',
  /** The zone's minute labels on the time axis (no box: they are clock times, not prices). */
  axisTick: '#93a4d6',
  axisTickBg: 'rgba(0, 0, 0, 0)',
  /** The panel's real volume bars before "now". */
  realVolume: '#5d6475',
  /** The legend's swatches (the panel's `aheadSheet.css` and the chart Key's): the band's two strengths, the hatch's
   * stripe, the ghost volume box's fill. */
  keyBand: 'linear-gradient(rgba(147, 164, 214, 0.18) 0 25%, rgba(147, 164, 214, 0.4) 25% 75%, '
    + 'rgba(147, 164, 214, 0.18) 75%)',
  keyHatchStripe: '#262c3d',
  keyBoxFill: 'rgba(147, 164, 214, 0.1)',
} as const;

/** Path alpha: scope All, and a strategy scope (a path that reaches the trigger, one that does not). */
export const AHEAD_PATH_ALPHA = { all: 0.34, reached: 0.6, missed: 0.07 } as const;
/** The fan is dimmed to this in a strategy scope so the coloured paths read first. */
export const AHEAD_FAN_DIM = 0.6;
export const AHEAD_DASH: { strategy: number[]; wall: number[] } = { strategy: [6, 4], wall: [] };

// ---------------------------------------------------------------- words

const pct = (x: number) => `${Math.round(x * 100)}%`;
const num2 = (x: number) => x.toFixed(2);
/** What an exam covered; one that does not say is never shown as a bare claim. */
const scopeOf = (scope: string | null) => scope ?? 'scope not stated';

/** One wall's "if it breaks" shares, as words take them (`aheadBreaks.breakWords`). */
export interface BreakWords {
  up: boolean;
  /** The wall by its one name, as its card headline has it: "4.69 · triple top" (`AHEAD_WORDS.wallName`). */
  wall: string;
  /** Its near edge (where a close back fails the break). */
  edge: string;
  share: number;
  n: number;
  /** The next wall beyond, "5.00 · HOD", and its price alone; null when there is none. */
  next: string | null;
  nextPrice: string | null;
  follow: number | null;
  /** Null when no path breaks. */
  fail: number | null;
  open: number | null;
}

/** The desk's chart Key: Ahead's section while it is on (the same marks as the Ahead panel's legend, and the chips,
 * the break line and the meet ring). Each row is a label and words that do not repeat it. */
export const AHEAD_KEY_TITLE = 'Ahead (AI view, not data)';
export const AHEAD_KEY_ROWS = {
  dash: { label: "Nova's lines", text: 'support and resistance carried on until they meet (no AI)' },
  ring: { label: 'Meet ring', text: "where Nova's two lines meet (no AI)" },
  band: { label: 'Likely range', text: "inner half, outer 80% of the forecaster's closes" },
  paths: { label: 'Paths', text: (n: number) => `${AHEAD_DRAWN_PATHS} of the forecaster's ${n}, drawn faint` },
  box: { label: 'AI volume', text: 'per minute: outline to its middle guess, whisker 10% to 90% (forecast)' },
  hatch: { label: 'Hatched zone', text: 'drawn, never recorded' },
  wallFirst: { label: '▲ / ▼ first', text: "share of paths reaching that wall first; neither: no wall in 15 min (forecast)" },
  breaks: { label: 'breaks … then', text: 'share of paths closing past the wall; of those, the share reaching the next '
    + 'wall and the share closing back (forecast)' },
} as const;

/** Every sentence Ahead shows, on the chart and in the panel. */
export const AHEAD_WORDS = {
  zoneTitle: 'AHEAD · next 15 min',
  aiTag: 'AI view, not data',
  now: (hhmm: string) => `now ${hhmm}`,
  newBadge: 'new',
  toggleLabel: 'Ahead',
  toggleTitle: 'Ahead: the next 15 minutes as the AI sees them (a forecast, never data). '
    + "Nova's own lines carried on to where they meet.",
  legendTitle: 'On the chart',
  legendLines: "Nova's lines carried on until they meet",
  legendRange: 'likely range: inner half, outer 80%',
  legendPaths: (n: number) => `16 of ${n} possible paths`,
  legendVolume: 'AI volume',
  legendHatch: 'hatched = drawn, never recorded',
  macdPaneLabel: "MACD worked out from the AI's paths",
  aiVolumeLabel: 'AI volume',

  // exam chips (the chart's chip and the panel's tag read the same words)
  passedTag: 'passed its exam',
  notPassedTag: 'has not passed its exam',
  scopeText: scopeOf,
  passed: (scope: string | null, days: number, moments: number) =>
    `passed its exam · ${scopeOf(scope)} · ${days} days, ${moments} moments`,
  notPassed: (volM: number, volB: number, rngM: number, rngB: number, band80: number, scope: string | null) =>
    `has not passed its exam · volume ${num2(volM)} vs ${num2(volB)} baseline · range ${num2(rngM)} vs ${num2(rngB)}`
    + ` · 80% range held ${pct(band80)} · ${scopeOf(scope)}`,
  noExam: 'no exam yet',
  examUnread: "says it passed its exam, but Nova could not read the exam",

  // states (the heading's main sentence)
  notSetUp: (reason: string | null) =>
    `No forecaster on this desk${reason ? ` (${reason})` : ''}. Nova's own lines still show.`,
  offline: (reason: string | null) =>
    `The forecaster is not answering${reason ? ` (${reason})` : ''}. Nova's lines still show.`,
  warming: "The forecaster is starting up. Nova's lines still show.",
  notEnoughBars: (need: number | null, have: number | null) =>
    `Ahead needs ${need ?? 30} one-minute candles today; this stock has ${have ?? 0}.`,
  quiet: (minutes: number | null) =>
    `No trade in the last ${minutes ?? 'few'} minutes: no new forecast until a candle closes.`,
  pending: 'Reading the minute that just closed…',
  error: (reason: string | null) => `Ahead has no forecast: ${reason ?? 'no reason given'}.`,
  hiddenNotPassed: 'AI view hidden: the forecaster has not passed its exam. Switch on '
    + "'Show before it has earned it' in the Ahead panel to see it anyway.",
  hiddenExamUnread: 'AI view hidden: the forecaster says it passed its exam, but Nova could not read that exam. '
    + "Switch on 'Show before it has earned it' in the Ahead panel to see it anyway.",
  linesOnly: 'Lines only: the AI view is off in this scope.',
  onlyOneMinute: 'Ahead draws on the 1-minute chart.',
  catchingUp: 'Catching up to the chart…',
  noRoom: 'No room at the right edge: the view is yours -- scroll right or go to the live edge.',
  replayEmpty: (sym: string) => `This replay holds no 1-minute candles for ${sym}.`,
  noCandles: 'Waiting for the first completed 1-minute candle.',
  asking: "Asking Nova's API for Ahead…",
  readLoading: "Reading Nova's levels and setups…",
  apiMissing: "Nova's API has no Ahead yet: restart the API after the update",
  apiUnreachable: "Could not reach Nova's API",
  readFailed: "Ahead could not read Nova's answer",
  apiStatus: (status: number) => `Nova's API answered HTTP ${status} for Ahead`,
  malformed: (field: string) => `the desk could not read ${field} in Nova's answer`,
  demoReason: "This demo has no forecaster: Ahead shows only Nova's own lines here",
  demoStatus: 'This demo has no forecaster',

  // Nova's lines to the meet
  linesNone: 'No holding support and resistance lines to carry on.',
  linesNoSupport: 'No holding support line under the price.',
  linesNoResistance: 'No holding resistance line over the price.',
  linesMet: 'The lines have already met, behind the newest candle.',
  linesNotClosing: 'The lines are not closing in.',
  meetAt: (hhmm: string) => `lines meet ≈ ${hhmm}`,
  meetIn: (candles: number) => `lines meet in ≈ ${candles} candles`,
  meetPast: (n: number, unit: 'min' | 'candles') => `lines meet past the zone (in ≈ ${n} ${unit})`,
  linesNote: "Nova's arithmetic, no AI. Slopes are rounded, so the meet is ≈.",

  // walls
  /** A wall's one name, on its chip, its card headline and its "if it breaks" line: its price and its label. */
  wallName: (price: string, label: string) => [price, label].filter(Boolean).join(' · '),
  noWalls: 'No level from the candles above and below the price to call a wall.',
  wallsOverlap: 'The walls above and below overlap: no wall-first odds.',
  wallFirst: (up: boolean, price: string, share: number) => `${up ? '▲' : '▼'} ${price} first · ${pct(share)} (forecast)`,
  neither: (share: number) => `neither in 15 min · ${pct(share)} (forecast)`,
  /** The same chips when the zone is too narrow for the words: the odds only, still inside the zone. */
  wallFirstShort: (up: boolean, share: number) => `${up ? '▲' : '▼'} ${pct(share)}`,
  neitherShort: (share: number) => `neither ${pct(share)}`,
  wallsTitle: 'Which wall first?',
  wallNeither: 'neither',
  sharesForecast: "Shares of the forecaster's paths: a forecast, not data.",
  wallsFoot: (n: number, by: string) => `Share of ${n} paths whose minute close reaches each wall first by ${by}. `
    + "From the forecaster's minute ranges joined by an assumed path shape, closes only (a wick is not seen), so "
    + 'the odds carry that assumption. The nearer wall wins more often: that is distance, not a call on direction.',
  byNote: 'The time counts from the newest candle, which can trail the clock on a thin stock.',

  // if it breaks (under every wall)
  breaksTitle: 'If it breaks',
  /** "If 4.69 · top breaks (38% of paths): 45% reach 5.00 · HOD first, 40% close back under 4.69, 15% still open
   * (forecast)" */
  breakLine: (b: BreakWords) => {
    const head = `If ${b.wall} breaks (${pct(b.share)} of paths)`;
    if (b.fail === null) return `${head}: none of the ${b.n} paths closes past it (forecast).`;
    const back = `${pct(b.fail)} close back ${b.up ? 'under' : 'over'} ${b.edge}`;
    if (b.next === null) {
      return `${head}: ${pct(b.open ?? 0)} hold ${b.up ? 'over' : 'under'} ${b.edge}, ${back} (forecast) · `
        + `no next wall ${b.up ? 'above' : 'below'} within reach`;
    }
    return `${head}: ${pct(b.follow ?? 0)} reach ${b.next} first, ${back}, ${pct(b.open ?? 0)} still open (forecast)`;
  },
  /** The wall chip's second line on the chart, a share before each word and never beside a price:
   * "breaks 38% · then 45% reach 5.00 · 40% back under". The card's line says the same in full. */
  breakChip: (b: BreakWords) => {
    const head = `breaks ${pct(b.share)}`;
    if (b.fail === null) return head;
    const back = `${pct(b.fail)} back ${b.up ? 'under' : 'over'}`;
    if (b.nextPrice === null) return `${head} · then ${pct(b.open ?? 0)} hold · ${back}`;
    return `${head} · then ${pct(b.follow ?? 0)} reach ${b.nextPrice} · ${back}`;
  },
  breaksNote: "A break is a minute close past the wall's far edge; back is a close past its near edge again. "
    + 'Shares of the paths that break.',
  breaksFoot: "A read of the forecaster's paths, not a signal: nothing here places an order.",

  // if it triggers
  notFollowed: "Nova is not watching this stock's setups",
  noLane: (family: string) => `No ${family} in play on the 1-minute chart.`,
  noLevels: (family: string) => `The ${family} has no complete trigger, entry, stop and target yet.`,
  triggered: (hhmm: string | null) => `Triggered${hhmm ? ` at ${hhmm}` : ''}: the plan card follows the trade`,
  provisional: 'forming: its levels may still move',
  reachShare: (share: number) => pct(share),
  reach: (n: number, trigger: string) => `of the ${n} paths reach the buy-stop ${trigger}`,
  triggerFoot: (by: string) => `Closes only; fills at the trigger. Of the paths that fill, which comes first by ${by}: `
    + 'target or stop.',
  targetFirst: (share: number) => `target first · ${pct(share)} (forecast)`,
  stopFirst: (share: number) => `stop first · ${pct(share)} (forecast)`,
  targetFirstShort: (share: number) => `target ${pct(share)}`,
  stopFirstShort: (share: number) => `stop ${pct(share)}`,
  triggerTitle: (family: string) => `If the ${family} triggers`,
  targetFirstLabel: (p: string) => `target ${p} first`,
  stopFirstLabel: (p: string) => `stop ${p} first`,
  stillOpen: 'still open',
  buyStop: (p: string) => `buy-stop ${p}`,
  stopAt: (p: string) => `stop ${p}`,
  targetAt: (p: string) => `target ${p}`,
  targetAtWall: (p: string) => `target ${p} · next wall`,

  // the panel
  sheetTitle: 'Ahead',
  sheetSub: 'next 15 min · redrawn every candle',
  /** One AI reads the whole chart. **All** is its view. A strategy asks it *"what if this triggers?"* */
  sheetLead: {
    before: 'One AI reads the whole chart. ',
    all: 'All',
    middle: ' is its view. A strategy asks it ',
    question: '"what if this triggers?"',
  },
  unearnedLabel: 'Show before it has earned it',
  unearnedNote: 'Off: the AI view shows only once the forecaster has passed its exam.',
  macdOff: 'MACD pane is off: no MACD fan',
  volumeTitle: 'Volume, next 15 min (forecast)',
  volumeLast: 'last 15 min (real)',
  volumeMiddle: (lo: string, hi: string) => `middle guess · ${lo} to ${hi}`,
  linesTitle: "Nova's lines",
  noAiTag: 'no AI',
  examTitle: "The forecaster's exam",
  examNone: 'No exam yet.',
  examUnknown: (reason: string) => `Exam unknown: ${reason}.`,
  noForecaster: (reason: string | null) => `No forecaster set up${reason ? ` (${reason})` : ''}.`,
  statusReading: "Reading the forecaster's status…",
  statusUnknown: "the forecaster's health could not be read",
  examVolume: 'Volume (ranks the busier stretches)',
  examRange: 'Range (ranks the wider stretches)',
  examWho: 'AI',
  examBand80: (x: number) => `80% range held ${pct(x)} (should be near 80%)`,
  examSample: (days: number, moments: number) => `Tested on ${days} days, ${moments} moments`,
  reportTitle: 'Report card',
  reportSince: (since: string | null, scored: number) => `${scored} scored since ${since ?? '—'}`,
  reportNone: 'Not scored yet: scoring starts when the forecaster answers.',
  reportBand80: 'Price stayed inside its 80% range',
  reportBand80Note: '(should be 80%)',
  reportVolume: 'Ranks the busier stretches',
  reportRange: 'Ranks the wider ranges',
  reportVsBaseline: '(1 = perfect, 0 = no better than chance)',
  reportDash: '—',
  reportFoot: 'Every forecast is checked by the forecaster once the 15 minutes it covers have closed.',
  forecast: 'forecast',
} as const;
