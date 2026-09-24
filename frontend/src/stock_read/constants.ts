/** The bot's read on one stock (ADR 036): the desk's numbers and words for it. */
import type { ReadState } from './types';

export const STOCK_READ_PATH = '/api/stock-read';
/** The read is polled while the Trader tab shows; the backend serves one read per 2 s. */
export const STOCK_READ_POLL_MS = 5_000;
export const STOCK_READ_DECISIONS_POLL_MS = 60_000;

/** The operator's risk per trade, for the plan's size (a desk setting, this window's browser). */
export const STOCK_READ_RISK_KEY = 'nova.stockRead.riskUsd';
export const STOCK_READ_RISK_DEFAULT_USD = 20;
export const STOCK_READ_RISK_MAX_USD = 10_000;
/** `{schema_version: 1, value: {setups, levels, hidden: string[], plan: 'auto' | 'open' | 'folded'}}`. */
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

export const LANE_LABELS: Record<string, string> = {
  first_pullback: 'FP',
  bull_flag: 'FLAG',
  flat_top_breakout: 'FLAT',
  red_to_green: 'R→G',
  hod_momo: 'HOD',
  market: 'MKT',
  bot: 'BOT',
};
