/** The bot's read on one stock (ADR 036): the desk's numbers and words for it. */
import type { ReadState } from './types';

export const STOCK_READ_PATH = '/api/stock-read';
/** The read is polled while the Trader tab shows; the backend serves one read per 2 s. */
export const STOCK_READ_POLL_MS = 5_000;
export const STOCK_READ_DECISIONS_POLL_MS = 60_000;
/** While you hold: trial T1's 30 s tape reading (`/flush`), read this often for the SELL NOW · FLUSH call. */
export const STOCK_READ_FLUSH_POLL_MS = 1_000;
/** A short plan's short check (ADR 048), read while the plan shows. */
export const STOCK_READ_SHORT_CHECK_POLL_MS = 5_000;
/** The flush call waits this long after you first held (trial T1: 10 s after the fill). */
export const STOCK_READ_FLUSH_AFTER_SEC = 10;
/** The day's setups that ended (ADR 036 amendment): read this often while the 1-minute pane shows, and
 * at once when a lane's drawn state changes. */
export const STOCK_READ_PAST_POLL_MS = 15_000;

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
/** Which zones a pane draws with a line and a label (the rest are ticks on the price axis): per side the
 * nearest and the strongest others within this share of the price, this many in all. */
export const LEVEL_MAP_WINDOW_PCT = 0.12;
export const LEVEL_DAILY_WINDOW_PCT = 0.4;
export const LEVEL_PER_SIDE = 3;

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
/** Which label keeps its room first: a seller on the book, then the high of day and the levels the day
 * made, then a round number. */
export const RULER_LABEL_RANK: Readonly<Record<string, number>> = {
  wall: 0, hod: 1, level: 2, vwap: 2, pmh: 2, open: 2, round: 3,
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
export const REPLAY_RAIL_NOTE = 'Sim replay: the charts draw the Sim eyes\' setups, the plan and the day\'s levels at the '
  + 'playhead. The tiles read the live feed, so they wait for the live edge.';
