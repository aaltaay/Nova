/**
 * Account page (approved UX redesign, second slice): labels, tunables and the
 * persisted-state contract. The page follows the header venue pills -- Live
 * shows the IBKR snapshot, Paper / Sim read Nova's practice ledger and its
 * history (GET /api/practice/history, AGENTS.md section 3).
 */
import type { PracticeVenue } from './practice';

/** GET ?venue=paper|sim&range=1D|5D|1M|3M|YTD|ALL -> the ledger as history. */
export const ACCOUNT_HISTORY_API_PATH = '/api/practice/history';
export const ACCOUNT_HISTORY_RANGES = ['1D', '5D', '1M', '3M', 'YTD', 'ALL'] as const;
export type AccountRange = (typeof ACCOUNT_HISTORY_RANGES)[number];
export const ACCOUNT_HISTORY_DEFAULT_RANGE: AccountRange = '1D';
export const accountHistoryPath = (venue: PracticeVenue, range: AccountRange): string =>
  `${ACCOUNT_HISTORY_API_PATH}?venue=${venue}&range=${range}`;
/** History is a derivation of the ledger; fills land every few seconds at most. */
export const ACCOUNT_HISTORY_POLL_MS = 5000;

/**
 * Persisted range preference. Owner: account/accountRangePref.ts.
 * Invalidation: schema bump -- an unknown schema_version is ignored, never
 * migrated by guesswork (persisted-state.mdc).
 */
export const ACCOUNT_RANGE_STORAGE_KEY = 'nova.account.range.v1';
export const ACCOUNT_RANGE_SCHEMA_VERSION = 1;

/** Ledger file the footer names (mirrors backend PRACTICE_PAPER_LEDGER_FILE). */
export const ACCOUNT_LEDGER_FILE: Record<PracticeVenue, string> = {
  paper: 'practice-paper.json',
  sim: 'practice-sim (scratch, in memory)',
};

/** Reconcile tolerance for "rows add up to Day's P&L" (cents). */
export const ACCOUNT_ROWS_TOLERANCE_USD = 0.005;

/** Bot positions cap the Risk block reads against (mirrors bot caps.max_shares default). */
export const ACCOUNT_RISK_GAUGE_SPAN_USD = 200;
/**
 * P&L smaller than this many dollars either way reads neutral, not red or
 * green (operator ask, 2026-09-22: a -$0.53 scratch trade should not look like
 * an alarm). Costs and cash movements are never tinted at all. The sign and
 * the figure are always shown; only the colour waits for a real move.
 */
export const PNL_TONE_MIN_USD = 5;

export const ACCOUNT_PAGE_TITLE = 'Account';
export const ACCOUNT_TAB_OVERVIEW = 'Overview';
export const ACCOUNT_TAB_BROKER = 'Broker snapshot';
export const ACCOUNT_TAB_REPORTS = 'Reports';

export const ACCOUNT_TAG_PRACTICE = 'Margin · practice';
export const ACCOUNT_TAG_LIVE = 'IBKR';
export const ACCOUNT_TAG_SIM_SCRATCH = 'Margin · scratch';

/* ---------- Account Details (left column) ---------- */
export const ACCOUNT_DETAILS_TITLE = 'Account Details';
export const ACCOUNT_TAV_LABEL = 'Total account value';
export const ACCOUNT_TAV_HIDDEN = '$•••,•••.••';
export const ACCOUNT_EYE_HIDE = 'Hide the account value';
export const ACCOUNT_EYE_SHOW = 'Show the account value';
export const ACCOUNT_TODAY_SUFFIX = 'today';
export const ACCOUNT_CARD_POSITIONS = 'Positions value';
export const ACCOUNT_CARD_CASH = 'Cash';
export const ACCOUNT_CARD_FLAT = 'flat · no open positions';
export const ACCOUNT_CASH_SUB: Record<PracticeVenue | 'live', string> = {
  live: 'settled · IBKR',
  paper: 'settled · practice',
  sim: 'scratch · rewinds with the playhead',
};
export const ACCOUNT_ROW_OPEN_PNL = 'Open P&L';
export const ACCOUNT_ROW_DAY_PNL = "Day's P&L";
export const ACCOUNT_ROW_REALIZED_TODAY = 'Realized today (net)';
export const ACCOUNT_ROW_BUYING_POWER = 'Buying power';
export const ACCOUNT_ROW_EXCESS_LIQUIDITY = 'Excess liquidity';
export const ACCOUNT_ROW_COMMISSIONS_TODAY = 'Commissions today';
export const ACCOUNT_ROW_FEES_TODAY = 'Regulatory fees today';
export const ACCOUNT_EXCESS_NA_PRACTICE = 'n/a · practice ledger has no maintenance margin';
export const ACCOUNT_ROWS_RECONCILE =
  "Realized is after commissions and fees: realized + open = Day's P&L";
export const ACCOUNT_ROWS_RESIDUAL = (diff: string): string =>
  `Rows differ from Day's P&L by ${diff}: Day's is measured from the 04:00 ET boundary, so a position carried in counts only its move since then.`;
export const ACCOUNT_ROWS_NO_HISTORY = "Realized, commissions and fees today come from the ledger history; it has not answered yet.";

export const ACCOUNT_DONUT_TITLE = 'Account Details';
export const ACCOUNT_DONUT_DROPDOWN = 'Cash balance';
export const ACCOUNT_DONUT_CENTER = 'Cash';
export const ACCOUNT_LEGEND_CASH = 'Cash';
export const ACCOUNT_LEGEND_POSITIONS = 'Positions (long)';
export const ACCOUNT_LEGEND_SHORT = 'Short value';
export const ACCOUNT_LEGEND_SHORT_NONE = 'none · no shorts on practice';
export const ACCOUNT_LEGEND_SHORT_NONE_LIVE = 'none held';
export const ACCOUNT_LEGEND_UNSETTLED = 'Unsettled';
export const ACCOUNT_LEGEND_UNSETTLED_NA = 'n/a on practice';
export const ACCOUNT_LEGEND_UNSETTLED_LIVE = 'not mirrored';

export const ACCOUNT_RISK_TITLE = 'Risk Level';
export const ACCOUNT_RISK_SAFE = 'Safe';
export const ACCOUNT_RISK_SOFT = 'Soft lock';
export const ACCOUNT_RISK_LOCKED = 'Locked';
export const ACCOUNT_RISK_UNKNOWN = 'No day P&L';
export const ACCOUNT_RISK_DAY_LOCK = 'Day P&L vs day lock';
export const accountRiskSoftLine = (usd: string): string => `${usd} soft · flatten, drop to L0`;
export const accountRiskHardLine = (usd: string): string => `${usd} hard · buys locked to midnight`;
export const ACCOUNT_RISK_BREAKERS = 'Breakers';
export const accountRiskBreakers = (tripped: number, armed: number): string =>
  `${tripped} tripped · ${armed} armed`;
export const ACCOUNT_RISK_BREAKERS_NOT_EXPOSED = 'not exposed · bot session unavailable';
export const ACCOUNT_ROW_LONG_VALUE = 'Long market value';
export const ACCOUNT_ROW_SHORT_VALUE = 'Short market value';

/* ---------- Performance ---------- */
export const ACCOUNT_PERF_TITLE = 'Performance';
export const ACCOUNT_PERF_TAB_ACCOUNT = 'Account P&L';
export const ACCOUNT_PERF_TAB_SYMBOL = 'Symbol P&L';
export const ACCOUNT_PERF_TAB_SOURCE = 'By source';
export const ACCOUNT_PERF_MODES = ['pnl', 'pct', 'value'] as const;
export type AccountPerfMode = (typeof ACCOUNT_PERF_MODES)[number];
export const ACCOUNT_PERF_MODE_LABELS: Record<AccountPerfMode, string> = {
  pnl: 'P&L',
  pct: 'P&L %',
  value: 'Account value',
};
/**
 * The headline is realized + open P&L (accountFigures.rangeNetPnl), so it says
 * both (QA R20) -- and that "open" is the live mark, the same figure Day's P&L
 * and the Symbol P&L total use (QA W1).
 */
export const accountPerfSubtitle = (range: AccountRange, opened: string | null): string =>
  range === 'ALL'
    ? `Since the ledger opened${opened ? ` · ${opened}` : ''} · realized + open at the live mark, net of commissions and fees`
    : `${range} · realized + open at the live mark, net of commissions and fees`;
export const ACCOUNT_PERF_LEGEND_MANUAL = 'Manual fill';
export const ACCOUNT_PERF_LEGEND_BOT = 'Bot fill';
export const ACCOUNT_PERF_LEGEND_EST = 'all fills';
export const ACCOUNT_PERF_LEGEND_EST_NOTE =
  'practice fills are Nova estimates (Paper: the live feed; Sim: the replay)';
export const ACCOUNT_PERF_EMPTY = 'No fills in this range · nothing to draw';
/**
 * The components cover this ledger's fills inside the range, so only ALL is
 * "since reset / since the ledger opened"; every other range says its range (C46).
 */
export const ACCOUNT_PERF_ROW_REALIZED = (range: AccountRange, since: string | null): string =>
  range !== 'ALL'
    ? `Net realized · ${range}`
    : since ? `Net realized since reset (${since})` : 'Net realized since the ledger opened';
export const ACCOUNT_PERF_ROW_COSTS = 'Of which commissions + fees';
export const ACCOUNT_SYMBOL_COL_SYMBOL = 'Symbol';
export const ACCOUNT_SYMBOL_COL_REALIZED = 'Gross';
export const ACCOUNT_SYMBOL_COL_OPEN = 'Open';
export const ACCOUNT_SYMBOL_COL_COSTS = 'Costs';
export const ACCOUNT_SYMBOL_COL_NET = 'Net';
export const ACCOUNT_SYMBOL_TOTAL = 'Total';
export const ACCOUNT_SYMBOL_FOOT = "Per-symbol P&L is read from the fills' symbol stamps; open P&L from the account's positions.";
export const ACCOUNT_SYMBOL_EMPTY = 'No fills in this range · nothing to attribute';
export const ACCOUNT_SOURCE_MANUAL = 'Manual';
export const ACCOUNT_SOURCE_BOT = 'Bot';
export const ACCOUNT_SOURCE_AUTO_PAPER = 'Auto Paper';
export const ACCOUNT_SOURCE_NO_FILLS = 'no fills';
export const ACCOUNT_SOURCE_NO_FILLS_NOTE = 'placed nothing in this range · stated, not zero';
export const ACCOUNT_SOURCE_AUTO_PAPER_NOTE = 'paper-shadow source (signal → confirm → auto_paper)';
export const accountSourceFills = (n: number): string => `${n} fill${n === 1 ? '' : 's'}`;
export const ACCOUNT_SOURCE_FOOT =
  'Nova stamps every fill with source and bot_id, so this split is read from the ledger, not inferred.';

/* ---------- Components ---------- */
export const ACCOUNT_COMPONENTS_TITLE = 'Components';
export const ACCOUNT_COMPONENTS_NOTE = 'ring = share of |total|';
export const ACCOUNT_COMP_REALIZED = 'Realized';
export const ACCOUNT_COMP_UNREALIZED = 'Unrealized';
export const ACCOUNT_COMP_COMMISSIONS = 'Commissions';
export const ACCOUNT_COMP_FEES = 'SEC + FINRA fees';
export const ACCOUNT_COMP_BOT = 'Bot share of P&L';
export const accountCompRoundTrips = (n: number): string =>
  n ? `${n} sell${n === 1 ? '' : 's'} · gross, before commissions and fees` : 'no sells in this range';
/** Components' Unrealized is the account's live-marked open P&L, like the headline (QA W1). */
export const ACCOUNT_COMP_UNREALIZED_NOTE = 'open positions at their live mark';
export const accountCompCommissions = (n: number): string => `${n} fill${n === 1 ? '' : 's'}`;
export const ACCOUNT_COMP_FEES_NOTE = 'sell-side pass-throughs';
export const accountCompBotShare = (pct: number | null): string =>
  pct == null ? 'no bot fills in this range · stated, not zero' : `${pct}% of gross realized`;
export const ACCOUNT_COMPONENTS_FOOT =
  'Every fill is stamped with its source and bot id. Interest, dividends and rewards do not exist on a practice ledger, so they are not drawn.';

/* ---------- Calendar ---------- */
export const ACCOUNT_CALENDAR_TITLE = 'Calendar · daily P&L';
export const ACCOUNT_CALENDAR_PREV = 'Previous month';
export const ACCOUNT_CALENDAR_NEXT = 'Next month';
export const ACCOUNT_CALENDAR_WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'] as const;
export const ACCOUNT_CALENDAR_NO_SESSION = 'no session';
export const ACCOUNT_CALENDAR_ARCHIVED = 'archived ledger';
export const ACCOUNT_CALENDAR_THIS_LEDGER = 'this ledger';
/** A blank weekday had no fill -- not "no session" (QA W5); weekends are dimmed and titled "no session". */
export const ACCOUNT_CALENDAR_BLANK = 'blank = no fills';
export const ACCOUNT_CALENDAR_EMPTY_MONTH = 'No ledger entries this month';

/* ---------- Ledger ---------- */
export const accountLedgerTitle = (id: string | null): string => (id ? `Ledger · ${id}` : 'Ledger');
export const ACCOUNT_RESET_BUTTON = 'Reset practice account';
export const ACCOUNT_STARTING_CASH = 'Starting cash';
export const ACCOUNT_RESET_HINT_PAPER =
  'Reset archives this ledger under the operator cache and opens a new one at starting cash. Nothing is deleted. Absent on Live.';
export const ACCOUNT_RESET_HINT_SIM =
  'The Sim scratch account resets when the replay unloads and unwinds when the playhead is scrubbed back.';
export const ACCOUNT_LEDGER_COL_TYPE = 'Type';
export const ACCOUNT_LEDGER_COL_ACTION = 'Action';
export const ACCOUNT_LEDGER_COL_TIME = 'Time (ET)';
export const ACCOUNT_LEDGER_COL_AMOUNT = 'Amount';
export const ACCOUNT_LEDGER_COL_BALANCE = 'Balance';
export const ACCOUNT_LEDGER_TYPE_FILL = 'Fill';
export const ACCOUNT_LEDGER_TYPE_ROLLOVER = 'Day rollover';
export const ACCOUNT_LEDGER_TYPE_START = 'Starting cash';
export const ACCOUNT_LEDGER_TYPE_RESET = 'Reset';
export const ACCOUNT_LEDGER_ROLLOVER_ACTION = 'Day P&L, commissions and fees reset to $0.00';
export const ACCOUNT_LEDGER_ROLLOVER_TAG = '04:00 ET';
export const ACCOUNT_LEDGER_START_ACTION = 'New ledger opened at starting cash';
export const accountLedgerResetAction = (file: string, realized: string): string =>
  `Previous ledger archived → ${file} (${realized})`;
export const ACCOUNT_LEDGER_EMPTY = 'No ledger entries in this range';
export const ACCOUNT_LEDGER_COMM = 'comm';
export const ACCOUNT_LEDGER_FEES = 'fees';
export const accountLedgerFoot = (file: string, schema: number, opened: string | null, archives: number): string =>
  `Ledger ${file} · schema ${schema}${opened ? ` · opened ${opened}` : ''} · archived ledgers: ${archives} · amounts are cash movement: price × qty, less commission and fees.`;
export const ACCOUNT_EST_CHIP = 'est';
export const ACCOUNT_EST_TITLE =
  "Filled by Nova's practice broker (Paper: against the live feed; Sim: against the replay), never an IBKR fill.";

/* ---------- Positions / Orders / Fills ---------- */
export const ACCOUNT_POS_TAB_POSITIONS = 'Positions';
export const ACCOUNT_POS_TAB_ORDERS = 'Orders (Today)';
export const ACCOUNT_POS_TAB_FILLS = 'Fills';
export const ACCOUNT_ORDER_FILTERS = ['working', 'filled', 'canceled', 'expired', 'all'] as const;
export type AccountOrderFilter = (typeof ACCOUNT_ORDER_FILTERS)[number];
export const ACCOUNT_ORDER_FILTER_LABELS: Record<AccountOrderFilter, string> = {
  working: 'Working',
  filled: 'Filled',
  canceled: 'Canceled',
  expired: 'Expired',
  all: 'All',
};
export const ACCOUNT_COL_TIME = 'Time';
export const ACCOUNT_COL_SYMBOL = 'Symbol';
export const ACCOUNT_COL_SIDE = 'Side';
export const ACCOUNT_COL_QTY = 'Qty';
export const ACCOUNT_COL_TYPE = 'Type';
export const ACCOUNT_COL_PRICE = 'Price';
export const ACCOUNT_COL_STATUS = 'Status';
export const ACCOUNT_COL_SOURCE = 'Source';
export const ACCOUNT_COL_AVG = 'Avg';
export const ACCOUNT_COL_LAST = 'Last';
export const ACCOUNT_COL_MKT_VALUE = 'Mkt value';
export const ACCOUNT_COL_UNREALIZED = 'Unrealized';
export const ACCOUNT_COL_COMM = 'Comm';
export const ACCOUNT_COL_FEES = 'Fees';
export const ACCOUNT_POSITIONS_EMPTY = 'Flat · no open positions';
export const ACCOUNT_ORDERS_EMPTY = 'No orders today';
export const ACCOUNT_FILLS_EMPTY = 'No fills in this range';
export const ACCOUNT_POS_FOOT =
  "Expired = a DAY order the session closed on at 20:00 ET; GTC orders persist. est = filled by Nova's practice broker (Paper: the live feed; Sim: the replay), never an IBKR fill.";
/** On Sim a DAY order expires at the replayed window's end, not 20:00 ET (QA W25). */
export const ACCOUNT_POS_FOOT_SIM =
  "Expired = a DAY order the replayed window closed on at its end; GTC orders persist. est = filled by Nova's practice broker against the replay, never an IBKR fill.";
export const ACCOUNT_POS_FOOT_LIVE = 'Working and closed orders as IBKR reports them for this session.';

/* ---------- Live absence / states ---------- */
export const ACCOUNT_LIVE_NO_LEDGER =
  "Live: no practice ledger -- performance history is the practice venues'. Switch the header venue pill to Paper or Sim to see the ledger.";
export const ACCOUNT_LIVE_ACCOUNT_LABEL = 'IBKR account';
export const ACCOUNT_LOADING = 'Account loading…';
export const ACCOUNT_HISTORY_LOADING = 'Ledger history loading…';
export const ACCOUNT_HISTORY_UNAVAILABLE = 'Ledger history unavailable';
export const ACCOUNT_PRACTICE_UNAVAILABLE = 'Practice account unavailable';
export const ACCOUNT_LIVE_UNAVAILABLE = 'IBKR account unavailable';
export const ACCOUNT_SIM_NOTHING_LOADED = 'Sim: nothing loaded · the scratch account starts with the replay';
export const ACCOUNT_WARNINGS_PREFIX = 'Archive warnings:';

/* ---------- QA batch: orders / account / safety (2026-09-22) ---------- */
/** Orders (Today) PRICE cell for an order with no price to show (a market order, unfilled) (V32). */
export const ACCOUNT_PRICE_NONE = '—';
export const ACCOUNT_PRICE_NONE_TITLE = 'Market order -- no limit price, and no fill price yet';
/** A history answer with no `components` -- the money itself is missing (C11). */
export const ACCOUNT_HISTORY_UNREADABLE = 'Nova answered an unreadable ledger history';

/* ---------- QA batch fix/qa2-account-practice-sim (2026-09-22) ---------- */
/**
 * Orders / Fills Source for the ADR 007 sources that are not manual / bot /
 * auto_paper -- each row names its own stamp, never a blanket "Nova" (QA W9).
 * `venue` is the practice broker's own cancel (buying power ran out at the fill).
 */
export const ACCOUNT_SOURCE_OTHER_LABELS: Record<string, string> = {
  flatten: 'Flatten',
  kill: 'KILL',
  cancel_working: 'Cancel working',
  approve: 'Approve',
  benchmark: 'Benchmark',
  venue: 'Practice broker',
  nova: 'Nova',
  ibkr: 'IBKR',
};
/** Live Fills: IBKR's order rows, one per filled order (QA W17). */
export const ACCOUNT_FILLS_FOOT_LIVE =
  "Live fills: one row per filled order at IBKR's average fill price, with the commission IBKR reported. Regulatory fees are not split out by IBKR.";
export const ACCOUNT_COMMISSIONS_PENDING_LIVE = 'IBKR has not reported every commission yet';
/**
 * Live Day's P&L is IBKR's RealizedPnL + UnrealizedPnL; the unrealized runs
 * from each position's cost, not from the day start (QA W18). Said, not hidden.
 */
export const ACCOUNT_DAY_PNL_LIVE_NOTE =
  "Live Day's P&L = IBKR realized today + open P&L from each position's cost: a position carried overnight counts its whole open P&L, not only today's move.";
/**
 * Risk: the bot's max-shares cap is the size of each bot order, not a position
 * limit, so it is shown as that and the largest position is labelled as every
 * source's (QA W11) -- the old "300 / 1 sh" meter compared the two.
 */
export const ACCOUNT_RISK_BOT_ORDER_SIZE = 'Bot order size';
export const accountRiskBotOrderSize = (cap: string): string => `${cap} sh per bot order`;
export const ACCOUNT_RISK_BOT_ORDER_SIZE_NONE = 'unavailable · bot session unavailable';
export const ACCOUNT_RISK_LARGEST_POSITION = 'Largest position';
export const accountRiskLargestPosition = (held: string, symbol: string | null): string =>
  held === '0' || !symbol ? 'flat · every source' : `${held} sh ${symbol} · every source`;
/** The sample desk's account is Nova Marketing Sample Data, not IBKR (QA W31). */
export const ACCOUNT_TAG_SAMPLE = 'Sample';
/** Orders (Today): a working order from an earlier day shows its date (QA W4). */
export const accountOrderStampOtherDay = (date: string, time: string): string => `${date} ${time}`;
