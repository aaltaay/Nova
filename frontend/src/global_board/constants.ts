/** The Global page's numbers and words (ADR 060). Periods and regions mirror backend/constants_global_board.py. */
import type { Basis, ColorBy, Period, RegionId, SessionState, Verdict } from './types';

export const GLOBAL_SCHEMA_VERSION = 1;
export const GLOBAL_BOARD_PATH = '/api/global/board';
/** The page asks this often while it shows; the backend reads each market on its own clock. */
export const GLOBAL_POLL_MS = 10_000;
/** While the first reads have not answered, ask again sooner. */
export const GLOBAL_LOADING_POLL_MS = 3_000;

export const GLOBAL_PERIODS: readonly Period[] = ['1D', '7D', '30D'];
export const PERIOD_LABEL: Record<Period, string> = { '1D': '1D', '7D': '7D', '30D': '30D' };
export const COLOR_BY_LABEL: Record<ColorBy, string> = { pressure: 'Pressure', move: 'Index move' };

/** The page's switches, remembered on this desk (a per-viewer convenience; never on the sample desk). */
export const GLOBAL_PREFS_STORAGE_KEY = 'nova.globalBoard.prefs.v1';
export const GLOBAL_PREFS_SCHEMA_VERSION = 1;

export const REGION_ORDER: readonly RegionId[] = ['americas', 'europe', 'middle_east_africa', 'asia_pacific'];
export const REGION_SHORT: Record<RegionId, string> = {
  americas: 'Americas',
  europe: 'Europe',
  middle_east_africa: 'Mid East',
  asia_pacific: 'Asia',
};

export const STATE_WORD: Record<SessionState, string> = {
  open: 'open',
  break: 'lunch break',
  closed: 'closed',
  holiday: 'holiday',
};

export const VERDICT_TONE: Record<Verdict, 'up' | 'down' | 'warn' | 'flat'> = {
  money_in: 'up',
  money_out: 'down',
  rotation: 'warn',
  quiet: 'flat',
};

export const BASIS_WORD: Record<Basis, string> = {
  index: 'index',
  future: 'index futures',
  etf: 'US-listed ETF',
};

/** The map's bubble radius (view units) for the biggest market's money traded; the smallest is GLOBAL_BUBBLE_MIN. */
export const GLOBAL_BUBBLE_MAX = 44;
export const GLOBAL_BUBBLE_MIN = 6;
/** The bars in "By exchange" run from minus to plus this percent of pressure, and this percent of index move. */
export const PRESSURE_BAR_SCALE_PCT = 30;
export const MOVE_BAR_SCALE_PCT: Record<Period, number> = { '1D': 2, '7D': 5, '30D': 10 };
/** The colour reaches full strength at this pressure / move (percent points). */
export const PRESSURE_FULL_PCT = 25;
export const MOVE_FULL_PCT: Record<Period, number> = { '1D': 1.5, '7D': 4, '30D': 8 };

/**
 * Where each market's label sits around its bubble on the map (view units from the bubble's centre, and the text
 * anchor), so the crowded corners -- Europe, East Asia -- stay readable. A market not listed labels above.
 */
export const LABEL_OFFSETS: Record<string, [number, number, 'start' | 'middle' | 'end']> = {
  us: [-58, 30, 'end'],
  ca: [-34, -40, 'end'],
  br: [16, 4, 'start'],
  uk: [-66, -26, 'end'],
  fr: [-48, 46, 'end'],
  de: [58, -34, 'start'],
  ch: [38, 40, 'start'],
  sa: [0, 26, 'middle'],
  za: [14, 4, 'start'],
  in: [-4, 54, 'end'],
  cn: [-58, -42, 'end'],
  hk: [-14, 46, 'middle'],
  tw: [40, 26, 'start'],
  kr: [-6, -52, 'end'],
  jp: [34, -18, 'start'],
  au: [16, 4, 'start'],
};

export const GLOBAL_TITLE = 'Global';
export const GLOBAL_SUBTITLE = "Where the world's stock money went";
export const GLOBAL_OFF = 'The Global page is turned off on this desk (NOVA_GLOBAL_BOARD=0).';
export const GLOBAL_OLD_API = "This desk's backend has no Global page yet -- restart it after the update.";
export const GLOBAL_REPLAY_NOTE = "Today's live markets (the Sim replay is not followed here)";
export const GLOBAL_LOADING = 'Reading each market from IBKR …';
/** Charts, the short check, the TraderTV exits and LULD always come first; the Market page takes turns with Global. */
export const GLOBAL_WAITING_HISTORY_FIRST = 'charts, bots, TraderTV and LULD go first';
export const GLOBAL_WAITING_LINES = 'Global waits for a spare market-data line to read the indexes.';
export const GLOBAL_HOW_TO_READ = 'How to read';
export const PRESSURE_DEF =
  'Pressure: money that traded in rising one-minute bars minus money in falling ones, from the real trades of ' +
  "the market's index futures in its own hours (or its US-listed ETF, named on the row).";
export const MOVE_DEF = "Index move: the market's main index against its last close.";
export const MIXED_DEF =
  'The two disagree: buyers were eager and the index still fell, or the reverse -- someone was absorbing the other side.';
export const SOURCES_DEF =
  'Every number is IBKR\'s: nothing here is estimated. Dollars are the trades\' notional at IBKR\'s exchange rates. ' +
  'A market IBKR refused says why.';
