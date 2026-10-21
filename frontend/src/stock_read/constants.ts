/** The bot's read on one stock (ADR 036): the desk's numbers and words for it. */
import type { ReadState } from './types';

export const STOCK_READ_PATH = '/api/stock-read';
/** The read is polled while the Trader tab shows; the backend serves one read per 2 s. */
export const STOCK_READ_POLL_MS = 5_000;
export const STOCK_READ_DECISIONS_POLL_MS = 60_000;
/** While you hold: trial T1's 30 s tape reading (`/flush`), read this often for the SELL NOW · FLUSH call. */
export const STOCK_READ_FLUSH_POLL_MS = 1_000;
/** While you hold: the big sellers and buyers on the held Level 2 line (#846), read this often. */
export const BOOK_WATCH_PATH = '/api/book-watch';
export const STOCK_READ_BIG_POLL_MS = 1_000;
/** A short plan's short check (ADR 048), read while the plan shows. */
export const STOCK_READ_SHORT_CHECK_POLL_MS = 5_000;
/** The flush call waits this long after you first held (trial T1: 10 s after the fill). */
export const STOCK_READ_FLUSH_AFTER_SEC = 10;
/** The day's setups that ended (ADR 036 amendment): read this often while the 1-minute pane shows, and
 * at once when a lane's drawn state changes. */
export const STOCK_READ_PAST_POLL_MS = 15_000;
/** Nova's LULD band step by step for the 1-minute chart (ADR 047 amendment 2026-10-12): `GET {path}/{symbol}/trail`,
 * read this often while Eyes is on. The band moves at most every 30 s; a halt ends it at once. */
export const LULD_TRAIL_PATH = '/api/luld';
export const LULD_TRAIL_POLL_MS = 2_000;

/* Risk per trade is the venue sleeve's (ADR 042 draft): read and saved by `setups/sleeveRisk.ts`, whose
 * numbers live in `constantGroups/setups.ts` (SLEEVE_*), since every proposal's Stage sizes by it too. */
/** `{schema_version: 1, value: {setups, levels, past, hidden: string[], plan: 'auto' | 'open' | 'folded'}}`. */
export const STOCK_READ_LAYERS_KEY = 'nova.stockRead.layers';
/** On `auto` the plan opens whole only when the quote card is at least this tall; below it the plan is
 * one line, so Level 2 keeps its room (at 1080p the whole plan left Level 2 about a third). */
export const STOCK_READ_PLAN_OPEN_MIN_PX = 560;

/** A decisions "show on chart" frames this much time around the event. */
export const STOCK_READ_FOCUS_BEFORE_SEC = 30 * 60;
export const STOCK_READ_FOCUS_AFTER_SEC = 15 * 60;

export const STATE_WORDS: Record<ReadState, string> = {
  ok: 'For it',
  bad: 'Against it',
  warn: 'Caution',
  unknown: 'Unknown',
  info: 'Fact',
};

export const TILE_NAMES: Record<string, string> = {
  in_play: 'In play',
  setups: 'Setups',
  front: 'Front',
  tape: 'Tape',
  short: 'Short',
  float: 'Float',
  halts: 'Halts',
};

/** A row's `source` is written in words by the backend, except the ids listed here: each reads as its
 * name on screen (`sec_edgar`: the float group's "Dilution on file"). */
const SOURCE_LABELS: ReadonlyMap<string, string> = new Map([
  ['sec_edgar', 'SEC EDGAR'],
]);

export function sourceLabel(source: string): string {
  return SOURCE_LABELS.get(source) ?? source;
}

/** Colours read for a long momentum trade (the account is long-only). */
export const STATE_COLORS: Record<ReadState, string> = {
  ok: '#30d158',
  warn: '#f59e0b',
  bad: '#ff453a',
  unknown: '#6b6b70',
  info: '#8e8e93',
};

export const SETUP_COLORS = {
  trigger: '#0a84ff',
  stop: '#ff453a',
  target: '#30d158',
  leg: 'rgba(10, 132, 255, 0.13)',
  legStroke: '#0a84ff',
  forming: 'rgba(245, 158, 11, 0.12)',
  formingStroke: '#f59e0b',
  risk: 'rgba(255, 69, 58, 0.18)',
  reward: 'rgba(48, 209, 88, 0.15)',
  faded: 'rgba(142, 142, 147, 0.12)',
  fadedStroke: '#8e8e93',
  level: '#8b92a5',
  round: '#f59e0b',
};

/** A setup's plan on the 1-minute chart (operator asks 2026-10-12): one box in the room right of the newest candle,
 * never a line across the pane (`strategyBoxRender.ts`). These are the forming setup's faint colours and the layout of
 * both; `STRATEGY_BOX_LIVE` holds the colours once the setup is near or armed. */
export const STRATEGY_BOX = {
  riskFill: 'rgba(255, 69, 58, 0.07)',
  rewardFill: 'rgba(48, 209, 88, 0.07)',
  outline: 'rgba(154, 160, 174, 0.35)',
  entryLine: 'rgba(10, 132, 255, 0.7)',
  name: 'rgba(214, 217, 224, 0.8)',
  when: 'rgba(154, 160, 174, 0.8)',
  entryInk: 'rgba(10, 132, 255, 0.9)',
  stopInk: 'rgba(255, 69, 58, 0.85)',
  targetInk: 'rgba(48, 209, 88, 0.85)',
  target2Ink: 'rgba(48, 209, 88, 0.65)',
  nameFont: '700 10px ui-sans-serif, system-ui, sans-serif',
  font: '500 10px ui-sans-serif, system-ui, sans-serif',
  /** It stands on its window when this much of it is left of the edge column's words, else it waits at the right
   * edge with `waitPx` of it clear of them. */
  minTextPx: 80,
  waitPx: 140,
  /** Room between the newest candle and the box, in candles. */
  gapBars: 1.5,
  /** Room inside the box around its words, and between them and the edge column's. */
  padPx: 6,
  /** The line height of its words. */
  lineH: 13,
  /** A view following the live edge slides to leave at least this much room right of the newest candle. */
  roomPx: 260,
  /** Target 2 in view: a dotted dash across the box at its price. */
  target2Dash: [2, 3],
} as const;

/** The box in full colour: a setup near or armed (operator ask 2026-10-12, option A of the mockups: "the
 * same box as before the open, in full colour"). Solid outline; the state word in its own colour. */
export const STRATEGY_BOX_LIVE = {
  riskFill: 'rgba(255, 69, 58, 0.16)',
  rewardFill: 'rgba(48, 209, 88, 0.16)',
  outline: 'rgba(201, 206, 216, 0.55)',
  entryLine: SETUP_COLORS.trigger,
  name: '#d6d9e0',
  when: '#9aa0ae',
  entryInk: SETUP_COLORS.trigger,
  stopInk: SETUP_COLORS.stop,
  targetInk: SETUP_COLORS.target,
  target2Ink: 'rgba(48, 209, 88, 0.8)',
  entryDash: [4, 3],
  entryWidth: 1.5,
  /** Behind its words: the entry line and the price's line run under them (the scene labels' backing). */
  wordBacking: 'rgba(12, 12, 14, 0.78)',
  state: { near: '#ffd60a', armed: SETUP_COLORS.target },
} as const;

/** The day's levels (ADR 036 amendment 2026-09-30): gold the half and whole dollars, coral a level over the
 * price, teal one under it, blue yesterday's, violet the daily chart's, purple VWAP. */
export const LEVEL_COLORS = {
  round: '#f59e0b',
  resistance: '#ff8a70',
  support: '#45c7b8',
  yesterday: '#8aa4d6',
  daily: '#b9a3e3',
  vwap: '#bf5af2',
} as const;
/** A round number and nothing else at its price is a faint solid hairline at this opacity, its label in full
 * colour (operator report 2026-10-12: the gold dashed lines were "too strong, too much"). A round at a top,
 * a bottom, VWAP or an old level takes that level's colour instead. */
export const LEVEL_ROUND_LINE_ALPHA = 0.4;
/** The trend lines (ADR 036 amendment 2026-10-12): brighter than the flat levels' colours so an angled line reads
 * apart from a horizontal one; a broken line is drawn at `brokenAlpha`, with no name at the edge (2026-10-13). */
export const TREND_COLORS = {
  support: '#34d399',
  resistance: '#ff9f43',
  brokenAlpha: 0.45,
} as const;

/** Which zones a pane draws with a line and a label (the rest are ticks on the price axis): per side the
 * nearest and the strongest others within this share of the price, this many in all. */
export const LEVEL_MAP_WINDOW_PCT = 0.12;
export const LEVEL_DAILY_WINDOW_PCT = 0.4;
export const LEVEL_PER_SIDE = 3;
/** One label per price (operator report 2026-10-13: "there are way too many lines here"): what sits within this share
 * of a stronger line folds into it -- its name joins that line's label, its card that line's card (`levelFold.ts`). */
export const LEVEL_FOLD_PCT = 0.01;

/** The flat top's own look (operator's sketch, 2026-10-06): the violet level the candles tap, each touch ringed
 * lavender, the base boxed violet, and the break and the hold candle green. Faded for a lane that is not the plan's. */
export const FLAT_TOP_COLORS = {
  line: '#a855f7',
  fill: 'rgba(168, 85, 247, 0.10)',
  ring: '#d8b4fe',
  ringStroke: '#a855f7',
  text: '#c4b5fd',
  go: '#30d158',
  holdFill: 'rgba(48, 209, 88, 0.06)',
} as const;
/** A flat top that is not the plan's: its own violet, dimmed, so it still reads as a flat top among the rest. */
export const FLAT_TOP_DIM = {
  line: 'rgba(168, 85, 247, 0.55)',
  fill: 'rgba(168, 85, 247, 0.06)',
  ring: 'rgba(216, 180, 254, 0.5)',
  ringStroke: 'rgba(168, 85, 247, 0.6)',
  text: 'rgba(196, 181, 253, 0.8)',
  go: 'rgba(48, 209, 88, 0.55)',
  holdFill: 'rgba(48, 209, 88, 0.04)',
} as const;
/** A flat top that failed: grey, like every faded lane. */
export const FLAT_TOP_FADED = {
  line: '#8e8e93',
  fill: 'rgba(142, 142, 147, 0.10)',
  ring: 'rgba(142, 142, 147, 0.45)',
  ringStroke: '#8e8e93',
  text: '#aeaeb2',
  go: '#8e8e93',
  holdFill: 'rgba(142, 142, 147, 0.06)',
} as const;
/** A past flat top's touches: rings as faint as its box. */
export const FLAT_TOP_PAST_RING = { stroke: 'rgba(168, 85, 247, 0.45)', fill: 'rgba(216, 180, 254, 0.30)' } as const;

/** The pullback dip (#847, watch only): pink, a colour no trade, level or other setup uses -- the pullback it
 * waits in, and the candle that bottomed it (`dipShapes.ts`). Dimmed when it is not the plan's; a failed one grey. */
export const DIP_COLORS = {
  line: '#f472b6',
  fill: 'rgba(244, 114, 182, 0.10)',
  ring: '#fbcfe8',
  candle: 'rgba(244, 114, 182, 0.16)',
  text: '#f9a8d4',
} as const;
export const DIP_DIM = {
  line: 'rgba(244, 114, 182, 0.5)',
  fill: 'rgba(244, 114, 182, 0.05)',
  ring: 'rgba(251, 207, 232, 0.5)',
  candle: 'rgba(244, 114, 182, 0.08)',
  text: 'rgba(249, 168, 212, 0.75)',
} as const;
export const DIP_FADED = {
  line: '#8e8e93',
  fill: 'rgba(142, 142, 147, 0.08)',
  ring: 'rgba(142, 142, 147, 0.45)',
  candle: 'rgba(142, 142, 147, 0.06)',
  text: '#aeaeb2',
} as const;
/** A past dip that triggered: its pullback faint and dashed, pink. */
export const DIP_PAST = { stroke: 'rgba(244, 114, 182, 0.5)', fill: 'rgba(244, 114, 182, 0.04)' } as const;

/** The ABCD (watch only): cyan, a colour no trade, level or other setup uses -- its swings through A, B and C, the
 * range they make and the two tolerances (`abcdShapes.ts`). Dimmed when it is not the plan's; a failed one grey. */
export const ABCD_COLORS = {
  line: '#64d2ff',
  fill: 'rgba(100, 210, 255, 0.06)',
  band: 'rgba(100, 210, 255, 0.14)',
  ring: '#0c0c0e',
  text: '#9be3ff',
  go: '#30d158',
} as const;
export const ABCD_DIM = {
  line: 'rgba(100, 210, 255, 0.45)',
  fill: 'rgba(100, 210, 255, 0.03)',
  band: 'rgba(100, 210, 255, 0.06)',
  ring: '#0c0c0e',
  text: 'rgba(155, 227, 255, 0.7)',
  go: 'rgba(48, 209, 88, 0.6)',
} as const;
export const ABCD_FADED = {
  line: '#8e8e93',
  fill: 'rgba(142, 142, 147, 0.05)',
  band: 'rgba(142, 142, 147, 0.08)',
  ring: '#0c0c0e',
  text: '#aeaeb2',
  go: '#8e8e93',
} as const;
/** A past ABCD: its range faint, cyan. */
export const ABCD_PAST = { stroke: 'rgba(100, 210, 255, 0.45)', fill: 'rgba(100, 210, 255, 0.03)' } as const;

/** A short setup that ended (ADR 049): its box orange and faint, its label ▼ SHORT in the outcome's ink. */
export const PAST_SHORT = {
  stroke: 'rgba(249, 115, 22, 0.55)', fill: 'rgba(249, 115, 22, 0.05)',
  legStroke: 'rgba(249, 115, 22, 0.35)', legFill: 'rgba(249, 115, 22, 0.03)', ink: '#fdba74',
} as const;

/** Setups that ended, drawn fainter than the live lane: red a rule broke, grey faded, green triggered. */
export const PAST_COLORS = {
  failed: { stroke: 'rgba(255, 69, 58, 0.55)', fill: 'rgba(255, 69, 58, 0.05)', ink: '#ff8a80' },
  faded: { stroke: 'rgba(142, 142, 147, 0.55)', fill: 'rgba(142, 142, 147, 0.05)', ink: '#aeaeb2' },
  triggered: { stroke: 'rgba(48, 209, 88, 0.55)', fill: 'rgba(48, 209, 88, 0.05)', ink: '#7ee2a0' },
  leg: { stroke: 'rgba(142, 142, 147, 0.35)', fill: 'rgba(142, 142, 147, 0.04)', ink: '#8e8e93' },
} as const;

export const LANE_LABELS: Record<string, string> = {
  first_pullback: 'FP',
  bull_flag: 'FLAG',
  flat_top_breakout: 'FLAT',
  flat_top_5m: 'FLAT 5M',
  red_to_green: 'R→G',
  gap_and_go: 'G&G',
  pullback_dip: 'DIP',
  abcd: 'ABCD',
  backside_lower_high: '▼ BACKSIDE',
  bear_flag: '▼ BEAR FLAG',
  failed_breakout: '▼ FAILED BO',
  lost_vwap: '▼ LOST VWAP',
  ssr_bounce: '▼ SSR BOUNCE',
  hod_momo: 'HOD',
  market: 'MKT',
  bot: 'BOT',
};

/** Who trades the stock (ADR 037): the switch's view, read while the Trader tab shows. */
export const STOCK_MODE_PATH = '/api/stock-mode';
export const STOCK_MODE_POLL_MS = 1_500;
/** `{schema_version: 1, value: boolean}`: false mutes the chart's ping. */
export const STOCK_MODE_SOUND_KEY = 'nova.stockRead.sound';
/** ENTER NOW stays up this long after the trigger, while the price is within this share of a risk. (Every
 * Nova entry's time limit is the sleeve's `working_ttl_sec`, read with the risk per trade.) */
export const ENTER_NOW_SEC = 30;
export const ENTER_NOW_RISK_SHARE = 0.5;
/** The plan ruler's labels (operator report 2026-10-01: ACN's 27 marks printed their prices on top of each
 * other): a label is about this wide per character at its 8px font, keeps this much room from the next, and
 * the ruler is taken to be this wide until it is measured. A label that would touch one already placed is
 * left off; its tick stays. */
export const RULER_LABEL_CHAR_PX = 4.6;
export const RULER_LABEL_GAP_PX = 6;
export const RULER_DEFAULT_WIDTH_PX = 600;
/** Which label keeps its room first: a seller on the book, then the targets (T1 / T2, #845) and the high of day,
 * then the levels the day made, then a round number. */
export const RULER_LABEL_RANK: Readonly<Record<string, number>> = {
  wall: 0, target: 1, hod: 1, level: 2, vwap: 2, pmh: 2, open: 2, round: 3,
};
/** What Nova just did (bought, sold, missed) stays in the chart's corner this long. */
export const NOVA_CALL_SEC = 30;
/** NOT A TRADE is one rule (spec H): it stops Nova's buys as well as the plan's own Stage. */
export const NOT_A_TRADE_NOVA = "It blocks Nova's buys too: the bot, Auto-entry and Approve do not take it.";
/** The words of the four modes, and the dot each wears (grey, blue, orange, orange). */
export const STOCK_MODE_COLORS = {
  signal: '#8e8e93',
  approve: '#0a84ff',
  auto_entry: '#ff9f0a',
  bot: '#ff9f0a',
} as const;

/** Who trades: notes shown on their own lines before the rest fold into "+N more" (Level 2 keeps its room). */
export const WHO_TRADES_NOTES_SHOWN = 3;

/** Level 2's short chips (ADR 048): SSR, the halt cool-off and where IBKR would liquidate the position. */
export const SHORT_CHIP_LIQ = 'LIQ';
export const SHORT_CHIP_COOLOFF = 'COOL-OFF';
export const SHORT_CHIP_SSR_TIP =
  'Under SSR a short sells only above the bid, so Nova prices it at the ask; not known counts as on. A cover is never held by it.';
export const SHORT_CHIP_COOLOFF_TIP =
  'No short for 10 minutes after an up-halt resumes: a stock that halted on its way up can halt again on its way up.';

/** The rail on a Sim replay (ADR 052): the chart draws the replay's read; the tiles are the live feed's. */
export const REPLAY_RAIL_NOTE = 'Sim replay: the charts draw the Sim eyes\' setups, the ones that ended, the plan and the '
  + 'day\'s levels at the playhead. The tiles read the live feed, so they wait for the live edge.';

/** The Key's card keeps inside its chart pane: it ends this far above the pane's bottom, scrolls past that, and is
 * never squeezed under this height (a pane too short for it lets it run on, still scrolling). */
export const KEY_CARD_PANE_MARGIN_PX = 8;
export const KEY_CARD_MIN_PX = 120;
