/**
 * Trader chrome labels (approved UX redesign, 2026-09-21): the one context
 * strip under the global bar, the Sim scrubber that rides on it, the Focus
 * rail, the compact Bot Autonomy card, the compact ticket and the drawer.
 * Every visible string lives here so the surfaces cannot drift apart.
 */

import { GATEWAY_STATUS_FAILED, GATEWAY_STATUS_PENDING } from './trader_view';

/* ── Context strip: symbol tabs ─────────────────────────────────────────── */

/** Tooltip on the whole strip -- replaces the permanent drag-hint sentence. */
export const TRADER_STRIP_TITLE =
  'Drag a tab onto another Nova window to dock it. Double-click a tab to pop it out.';
export const TRADER_STRIP_TITLE_FLOAT =
  'Drag a tab onto the main Nova window to dock it.';
export const TRADER_TAB_RECORDING_TITLE = 'Recording';
export const TRADER_TAB_CLOSE_ARIA = 'Close';
export const TRADER_TAB_CLOSE_RECORDING_TITLE = 'Stop recording before closing this tab';
/** Catalyst chip on a tab or a Focus row. Nova has a headline, not a category. */
export const TRADER_CATALYST_NEWS = 'NEWS';
export const TRADER_CATALYST_PR = 'PR';
/** Bad news from the catalyst verdict (ADR 024): an offering, or a delisting / reverse split. */
export const TRADER_CATALYST_DILUTION = 'DILUTION';
export const TRADER_CATALYST_SPLIT = 'SPLIT';
export const TRADER_CATALYST_NONE = 'no news';
/** Wire names whose headlines are the company's own release. */
export const TRADER_CATALYST_PR_SOURCES = [
  'pr newswire', 'prnewswire', 'globenewswire', 'business wire', 'businesswire', 'accesswire',
] as const;
export const TRADER_STRIP_OVERFLOW_TITLE = 'More tabs';
export const TRADER_STRIP_OVERFLOW_ARIA = 'Show tabs that do not fit';

/* ── Context strip: Sim scrubber ────────────────────────────────────────── */

export const SIM_STRIP_LABEL = 'Sim session';
export const SIM_STRIP_TRANSPORT_FIRST = 'Jump to the first recorded second';
export const SIM_STRIP_TRANSPORT_BACK = 'Back 1 minute';
export const SIM_STRIP_TRANSPORT_FORWARD = 'Forward 1 minute';
export const SIM_STRIP_TRANSPORT_EDGE = 'Jump to the live edge (follow the wall clock)';
export const SIM_STRIP_STEP_MINUTES = 1;
export const SIM_STRIP_MENU_ARIA = 'Sim session menu';
export const SIM_STRIP_MENU_FOLLOW = 'Follow wall clock';
export const SIM_STRIP_MENU_LOAD_RECORDING = 'Load recording';
export const SIM_STRIP_MENU_CLOSE_REPLAY = 'Close replay';
export const SIM_STRIP_MENU_DAY = 'Day';
export const SIM_STRIP_MENU_TICKER = 'Ticker';
export const SIM_STRIP_MENU_NO_RECORDING = 'No recording';
export const SIM_STRIP_MENU_PICK_TICKER = 'Pick ticker';
export const SIM_STRIP_REPLAY_PAUSED = 'Replay · paused';
export const SIM_STRIP_REPLAY_PLAYING = 'Replay';
export const SIM_STRIP_REPLAY_FAILED = 'Replay failed';
export const SIM_STRIP_RTH_OPEN = '09:30';
export const SIM_STRIP_RTH_CLOSE = '16:00';
/**
 * Regular hours as fractions of the default 04:00-20:00 session -- only while
 * the clock has not stated its window; otherwise `stripScale` places the ticks
 * on the clock's own bounds.
 */
export const SIM_STRIP_RTH_OPEN_FRACTION = (9.5 - 4) / 16;
export const SIM_STRIP_RTH_CLOSE_FRACTION = (16 - 4) / 16;
/** Past this fraction the playhead tag flips to the left of the marker. */
export const SIM_STRIP_TAG_FLIP_FRACTION = 0.84;
export const simStripFailedTitle = (error: string): string => `Replay failed: ${error}`;

/* ── Quote card venue tag ───────────────────────────────────────────────── */

export const TRADER_VENUE_TAG_PAPER = 'PAPER';
export const TRADER_VENUE_TAG_SIM = 'SIM';
export const TRADER_VENUE_TAG_LIVE_EDGE = 'live edge';
export const TRADER_VENUE_TAG_REPLAY = 'replay';
export const TRADER_VENUE_TAG_FILLS = 'fills';
export const TRADER_EST_CHIP = 'est';
export const TRADER_EST_CHIP_TITLE =
  'Practice fill, estimated locally against the reference tape -- never a broker execution.';
export const TRADER_VENUE_TAG_PAPER_TITLE =
  "Nova's practice account on the live feed: fake money, fills estimated locally, never an IBKR place.";
export const TRADER_VENUE_TAG_SIM_TITLE =
  'Sim scratch account: fills estimated against the loaded replay (the live feed at the live edge); '
  + 'scrubbing back unwinds them.';

/* ── Bot Autonomy card ──────────────────────────────────────────────────── */

export const BOT_CARD_TITLE = 'Bot autonomy';
export const BOT_CARD_SETUP_INFO_ARIA = 'What this setup trades';
export const BOT_CARD_ALLOWLIST_TITLE = 'Symbols the bot may act on';

/* ── Compact ticket ─────────────────────────────────────────────────────── */

export const TICKET_HEADER_FILLS_ESTIMATED = 'fills estimated';
/** The Live venue has no practice tag; the header still names where the order goes. */
export const TICKET_VENUE_LIVE = 'LIVE';
export const TICKET_VENUE_LIVE_TITLE = 'Live venue: a placed order goes to IBKR.';
export const TICKET_TIF_LABEL = 'TIF';
export const TICKET_TIF_DAY = 'DAY';
export const TICKET_TIF_GTC = 'GTC';
export const TICKET_TIF_TITLE = 'Time in force for the next order (also Settings > Trade)';
export const TICKET_PRICE_LABEL = 'Price';
export const TICKET_STOP_LABEL = 'Stop';
export const TICKET_TRAIL_LABEL = 'Trail $';
export const TICKET_PRICE_BID = 'Bid';
export const TICKET_PRICE_MID = 'Mid';
export const TICKET_PRICE_ASK = 'Ask';
export const TICKET_PRICE_QUICK_ARIA = 'Keep the price on the top of book';
/** `${TITLE} ask: 5.14` -- a click keeps the limit on that side as Level 2 moves. */
export const TICKET_PRICE_QUICK_TITLE = 'Follow the live';
export const TICKET_PRICE_FOLLOWING_TITLE = 'Following the live';
export const TICKET_PRICE_FOLLOW_STOP = 'type a price, or click again, to stop';
export const TICKET_PRICE_QUICK_NO_BOOK = 'No live bid / ask for this symbol';
/** Said while the ticket follows a side the book has stopped showing. */
export const TICKET_PRICE_FOLLOW_HOLDING = 'the price holds until the book returns';
/** Lead of the one-line reason shown only while Market is greyed out. */
export const TICKET_MARKET_UNAVAILABLE = 'Market unavailable';
export const TICKET_COST_LABEL = 'Cost';
export const TICKET_BP_AFTER_LABEL = 'BP after';
export const TICKET_COST_TITLE =
  'Estimate: shares × price before commissions; buying power after is a plain subtraction '
  + '(margin not modelled). A dash means Nova cannot work it out yet.';
export const TICKET_COST_UNKNOWN = '—';
export const TICKET_LAST_LABEL = 'Last:';
export const QUICK_TRADES_ARIA = 'Quick trades';
export const QUICK_TRADES_CUSTOMIZE_TITLE = 'Customize quick trades (Settings > Hot Keys)';
export const QUICK_TRADES_CUSTOMIZE_ARIA = 'Customize quick trades';
/**
 * Short labels under the quick-trade icons, one per action kind. The full
 * action name (and its key chord) is the tooltip. `{n}` shares, `{p}` percent,
 * `{c}` the offset in cents.
 */
export const QUICK_TRADES_SHORT_LABELS = {
  cancel_symbol: 'Cxl sym',
  cancel_and_exit: 'Cxl+Flat',
  cancel_all_orders: 'Cxl all',
  exit_pos: 'Flatten',
  exit_pos_pct: 'Exit {p}%',
  buy_market: 'B{n} MKT',
  buy_limit_ask_offset: 'B{n} Ask+{c}',
  sell_limit_bid_offset: 'S{n} Bid−{c}',
  sell_limit_ask_offset: 'S{n} Ask+{c}',
  sell_pos_pct_ask: 'Sell {p}%',
  sell_pos_pct_bid_offset: 'S{p}% Bid−{c}',
} as const;
/** `Sell 100%` reads as one word at the rail's width. */
export const QUICK_TRADES_SELL_ALL_LABEL = 'Sell all';

/* ── Focus rail ─────────────────────────────────────────────────────────── */

export const FOCUS_RAIL_TITLE = 'Focus';
export const FOCUS_RAIL_ARIA = 'Focus list';
export const FOCUS_RAIL_PICK_ARIA = 'Mirror a scanner list';
export const FOCUS_RAIL_COLLAPSE = 'Collapse focus list';
export const FOCUS_RAIL_EXPAND = 'Expand focus list';
export const FOCUS_RAIL_FOOTER_KEYS = '↑ ↓';
export const FOCUS_RAIL_FOOTER_CYCLE = 'to cycle ·';
export const FOCUS_RAIL_FOOTER_ENTER = 'Enter';
export const FOCUS_RAIL_FOOTER_OPENS = 'opens';
export const FOCUS_RAIL_NO_FEED = 'No scanner feed in this window';
export const focusRailNotMirrored = (title: string): string =>
  `${title} is not mirrored here yet -- open it on the Scanner`;
export const focusRailEmpty = (title: string): string => `${title}: no rows right now`;
/** The operator's watch list with nothing on it (watch_list/). */
export const FOCUS_RAIL_WATCH_EMPTY = 'Nothing on your watch list yet. Right-click a ticker to add one.';
export const focusRailMore = (count: number): string => `${count} more ↓`;
export const FOCUS_RAIL_BOT_HELD_TITLE = 'Allowlisted · depth line held';
export const FOCUS_RAIL_BOT_QUIET_TITLE = 'Allowlisted · quiet (no depth line)';
export const FOCUS_RAIL_REC_TITLE = 'Recording';
/** localStorage: collapsed flag + mirrored list (versioned; older shapes are ignored). */
/** Focus rail column headers: click sorts, again flips, a third click returns
 * to the list's own order. */
export const FOCUS_RAIL_SORT_LABELS = { symbol: 'Sym', price: 'Last', gap: '%', news: '●' } as const;
export const FOCUS_RAIL_SORT_TITLES = {
  symbol: 'Sort by symbol',
  price: 'Sort by last price',
  gap: 'Sort by % change',
  news: 'Sort by news: freshest catalyst first (ties: biggest % first)',
} as const;
export const FOCUS_RAIL_SORT_RESET = "click again for the list's own order";
/** Focus rail hover cards: what a row's circles mean, in plain words. */
export const FOCUS_RAIL_CARD_HIDE_MS = 200;
export const FOCUS_RAIL_CARD_MAX_ITEMS = 5;
export const FOCUS_RAIL_CARD_GAP_PX = 8;
export const focusRailNewsCardTitle = (symbol: string): string => `${symbol} · News since the prior close`;
export const focusRailCardMoreItems = (count: number): string => `+${count} more in the Trader's News panel`;
export const FOCUS_RAIL_CARD_NEWS_UNAVAILABLE = 'This desk cannot read the news list; showing what the scanner row carries.';
export const FOCUS_RAIL_CARD_NO_HEADLINE = 'No headline in the last 24 hours on the scanner row.';
export const focusRailCardNewestHeadline = (ago: string): string => `Newest headline ${ago}`;
export const focusRailStatusCardTitle = (symbol: string): string => `${symbol} · Status`;
export const FOCUS_RAIL_CARD_REC_HEAD = 'Recording';
export const FOCUS_RAIL_CARD_REC_BODY =
  'Nova is recording this symbol\'s tape and Level 2 to disk (Session Record), so the session can be replayed in Sim.';
export const FOCUS_RAIL_CARD_BOT_HELD_HEAD = 'Bot allowlist · watching';
export const FOCUS_RAIL_CARD_BOT_HELD_BODY =
  'On the bot allowlist, and Nova holds its Level 2 line (an open Trader tab or a recording), so the bot can see it. '
  + 'Any bot entry still passes the gates on the Bots page.';
export const FOCUS_RAIL_CARD_BOT_QUIET_HEAD = 'Bot allowlist · quiet';
export const FOCUS_RAIL_CARD_BOT_QUIET_BODY =
  'On the bot allowlist, but Nova holds no Level 2 line for it, so the bot cannot act on it. '
  + 'Open it in a Trader tab or record it to give the bot eyes.';
export const FOCUS_RAIL_STORAGE_KEY = 'nova.trader.focusRail.v1';
export const FOCUS_RAIL_DEFAULT_LIST = 'gappers';

/* ── Positions / Orders drawer ──────────────────────────────────────────── */

export const DRAWER_TAB_ORDERS = 'Orders · today';
export const DRAWER_TABS_ARIA = 'Positions and orders';
export const DRAWER_FILTERS_ARIA = 'Orders today filter';
export const DRAWER_COLLAPSE = 'Collapse';
export const DRAWER_EXPAND = 'Expand';
export const DRAWER_SAMPLE_SHOW = 'Show sample';
export const DRAWER_SAMPLE_HIDE = 'Hide sample';
export const DRAWER_SAMPLE_TAG = 'Sample';
export const DRAWER_POSITION_LABEL = 'Position';
export const DRAWER_UNREALIZED_LABEL = 'unrealized';
export const DRAWER_NO_POSITION = 'No open position';
export const DRAWER_UNREALIZED_UNKNOWN = '—';
export const DRAWER_SIM_NOTE = 'Sim scratch account · rewinds with the playhead';
export const DRAWER_PAPER_NOTE = 'Nova Paper · fake money on the live feed';
export const DRAWER_LIVE_NOTE = 'IBKR live account';

/* ── QA batch fix/qa-sim-replay (2026-09-22): practice ticket cost line (V24) ── */

/** A SELL only reduces a held long: from flat, or past the held quantity, nothing fills. */
export const TICKET_COST_NO_POSITION =
  'Nothing to sell: a SELL only reduces a held position, and Nova never opens a short from it.';
/** The Sim venue tag's state word with nothing loaded off the edge (V38: it read "replay"). */
export const TRADER_VENUE_TAG_NO_REPLAY = 'no replay';

// ── QA batch: Scanner / HOD / desk honesty (2026-09-22) ────────────────────
/** Venue names for the drawer's sample banner (QA V22). */
const DRAWER_SAMPLE_VENUE: Record<string, string> = { live: 'Live', paper: 'Paper', sim: 'Sim' };
/**
 * The drawer's sample banner names the venue: sample rows replace this
 * venue's real orders while they show -- they were mixed in and counted
 * with them, and labelled "paper-style ... not from IBKR" even on Sim (QA V22).
 */
export function drawerSampleBanner(mode: string): string {
  const venue = DRAWER_SAMPLE_VENUE[mode];
  return venue
    ? `Sample data -- not your ${venue} orders. Your real orders are hidden while the sample shows.`
    : 'Sample data -- not real orders. Your real orders are hidden while the sample shows.';
}

/* ── QA batch fix/qa2-account-practice-sim (2026-09-22): drawer footer ── */
/**
 * The footer with no symbol selected (the Scanner before a row is picked):
 * it read "No open position ·" with nothing after it while the Positions tab
 * listed three (QA W29).
 */
export const DRAWER_NO_SYMBOL = 'No symbol selected';
export const drawerOpenPositions = (n: number): string =>
  n === 0 ? 'flat' : `${n} open position${n === 1 ? '' : 's'} in Positions`;

/* ── Why a trading control is locked (2026-09-23) ──────────────────────────
 * Shown by ux/whyTip.ts on hover and on a refused press, from `data-why`. */

/** `/api/ibkr/status` says the Gateway session is not usable (Paper needs the feed too). */
export const WHY_GATEWAY_NOT_CONNECTED = 'IB Gateway is not connected -- reconnect it from the header.';
/**
 * The status request is pending or failing (QA D10 on the ticket, #459): the
 * Gateway's state is unknown, so the ticket says that -- never "Connect IB
 * Gateway" -- in the depth card's words (trader_view.ts).
 */
export const WHY_GATEWAY_STATUS_PENDING = `${GATEWAY_STATUS_PENDING}.`;
export const WHY_GATEWAY_STATUS_FAILED = `${GATEWAY_STATUS_FAILED} -- orders wait for it.`;
/** The ticket's Place button while the Gateway is not usable, by what the status knows. */
export const TICKET_CONNECT_GATEWAY_LABEL = 'Connect IB Gateway';
export const TICKET_GATEWAY_CHECKING_LABEL = 'Checking IB Gateway…';
export const TICKET_GATEWAY_UNKNOWN_LABEL = 'IB Gateway state unknown';
/** The ticket's own order is in flight; Live, Paper and Sim each answer it. */
export const TICKET_WHY_SENDING = 'Sending the order -- the ticket unlocks when the venue answers.';
