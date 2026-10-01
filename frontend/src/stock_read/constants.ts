/** The bot's read on one stock (ADR 036): the desk's numbers and words for it. */
import type { ReadState } from './types';

export const STOCK_READ_PATH = '/api/stock-read';
/** The read is polled while the Trader tab shows; the backend serves one read per 2 s. */
export const STOCK_READ_POLL_MS = 5_000;
export const STOCK_READ_DECISIONS_POLL_MS = 60_000;
/** While you hold: trial T1's 30 s tape reading (`/flush`), read this often for the SELL NOW · FLUSH call. */
export const STOCK_READ_FLUSH_POLL_MS = 1_000;
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
  red_to_green: 'R→G',
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
