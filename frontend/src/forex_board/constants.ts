/** The Forex page's numbers and words (ADR 061). Periods mirror backend/constants_forex_board.py. */
import type { ColorBy, Period, Verdict } from './types';

export const FOREX_SCHEMA_VERSION = 1;
export const FOREX_BOARD_PATH = '/api/forex/board';
/** The page asks this often while it shows; the backend reads each currency on the FX day's clock. */
export const FOREX_POLL_MS = 10_000;
/** While the first reads have not answered, ask again sooner. */
export const FOREX_LOADING_POLL_MS = 3_000;

export const FOREX_PERIODS: readonly Period[] = ['1D', '7D', '30D'];
export const PERIOD_LABEL: Record<Period, string> = { '1D': '1D', '7D': '7D', '30D': '30D' };
export const COLOR_BY: readonly ColorBy[] = ['strength', 'futures'];
export const COLOR_BY_LABEL: Record<ColorBy, string> = { strength: 'Strength', futures: 'Futures' };

/** The page's switches, remembered on this desk (a per-viewer convenience; never on the sample desk). */
export const FOREX_PREFS_STORAGE_KEY = 'nova.forexBoard.prefs.v1';
export const FOREX_PREFS_SCHEMA_VERSION = 1;

export const VERDICT_TONE: Record<Verdict, 'up' | 'down' | 'warn' | 'flat'> = {
  safe_havens: 'warn',
  risk_on: 'up',
  dollar_bought: 'flat',
  dollar_sold: 'flat',
  quiet: 'flat',
};

/** The eight majors' pairs (row against column); the list holds every currency. */
export const MAJORS = ['USD', 'EUR', 'JPY', 'GBP', 'CHF', 'CAD', 'AUD', 'NZD'] as const;

/** The map's bubble radius (view units) for the biggest currency's daily trading (the dollar); the smallest is MIN. */
export const FOREX_BUBBLE_MAX = 44;
export const FOREX_BUBBLE_MIN = 4.5;
/** The bars in the list run from minus to plus this much strength / futures pressure (percent points). */
export const STRENGTH_BAR_SCALE_PCT: Record<Period, number> = { '1D': 0.8, '7D': 2, '30D': 4 };
export const FUTURES_BAR_SCALE_PCT = 30;
/** The colour reaches full strength at this strength / futures pressure. */
export const STRENGTH_FULL_PCT: Record<Period, number> = { '1D': 0.6, '7D': 1.5, '30D': 3 };
export const FUTURES_FULL_PCT = 25;
/** Follow the sun: an hour's colour is full at this strength change / futures pressure. */
export const SUN_FULL_STRENGTH = 0.12;
export const SUN_FULL_FUTURES = 30;
/** Major pairs: a cell's colour is full at this move (percent). */
export const PAIR_FULL_PCT: Record<Period, number> = { '1D': 1, '7D': 2.5, '30D': 5 };

/**
 * Where each currency's label sits around its bubble on the map (view units from the bubble's centre, and the text
 * anchor), so the crowded corners -- Europe, East Asia, North America -- stay readable (mockup v2). A currency not
 * listed labels above.
 */
export const LABEL_OFFSETS: Record<string, [number, number, 'start' | 'middle' | 'end']> = {
  USD: [-56, 4, 'end'],
  CAD: [-30, -44, 'end'],
  MXN: [-16, 16, 'end'],
  BRL: [14, 4, 'start'],
  GBP: [-60, -18, 'end'],
  EUR: [-52, 44, 'end'],
  CHF: [44, 44, 'start'],
  SEK: [40, -30, 'start'],
  NOK: [-34, -36, 'end'],
  ZAR: [14, 4, 'start'],
  INR: [-14, 4, 'end'],
  CNY: [-58, -24, 'end'],
  KRW: [2, -38, 'middle'],
  JPY: [34, -22, 'start'],
  TWD: [40, 24, 'start'],
  HKD: [-38, 26, 'end'],
  SGD: [-22, 30, 'end'],
  AUD: [-24, 4, 'end'],
  NZD: [-4, 32, 'end'],
};

export const FOREX_TITLE = 'Forex';
export const FOREX_SUBTITLE = "Where the world's currency money went";
export const FOREX_OFF = 'The Forex page is turned off on this desk (NOVA_FOREX_BOARD=0).';
export const FOREX_OLD_API = "This desk's backend has no Forex page yet -- restart it after the update.";
export const FOREX_REPLAY_NOTE = "Today's live market (the Sim replay is not followed here)";
export const FOREX_LOADING = 'Reading each currency from IBKR …';
export const FOREX_WAITING_HISTORY_FIRST = 'charts, bots, TraderTV and LULD go first';
export const FOREX_WAITING_LINES = 'Forex waits for a spare market-data line to read the spot prices.';
export const FOREX_CLOSED = 'The FX market is closed for the weekend';
export const FOREX_HOW_TO_READ = 'How to read';
export const SIZE_DEF =
  "A day: the BIS survey's daily average for April 2025 -- every trade the currency is on one side of, spot, forwards, " +
  'swaps and options together. Each trade has two currencies, so the shares add to 200%. Published every three ' +
  'years, not live: forex has no exchange, and no feed sees its total.';
export const STRENGTH_DEF =
  "Strength: the currency against an even mix of the others IBKR prices, from IBKR's spot prices since the FX day " +
  'began at 17:00 New York. Each pair\'s move is worked out from the two currencies\' moves against the dollar.';
export const FUTURES_DEF =
  'Futures: money that traded in rising one-minute bars minus money in falling ones, from each currency\'s CME future ' +
  '-- the public part of forex, about 1% of it. Every one trades against the dollar, so the dollar\'s row is the ' +
  'other side of all of them.';
export const MIXED_DEF =
  'The two disagree: futures buyers were eager and the currency still fell, or the reverse -- someone was taking the ' +
  'other side.';
export const SOURCES_DEF =
  "Every number but the sizes is IBKR's, and nothing here is estimated. A currency IBKR has no price for says so.";
