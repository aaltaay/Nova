import {
  SHORT_SETUP_IDS,
  SHORT_SETUP_LABELS,
  SHORT_SETUP_TAGS,
} from './short_setups';

/** Bot localhost API tunables -- mirrors backend/constants_bot.py. */
export const BOT_ACTION_KINDS = [
  'buy_market',
  'buy_limit_ask_offset',
  'sell_limit_bid_offset',
  'sell_limit_ask_offset',
  'exit_pos',
  'cancel_symbol',
  'exit_pos_pct',
  'sell_pos_pct_ask',
  'sell_pos_pct_bid_offset',
  // ADR 049 (#778 step 5): a short goes in with its buy stop; a cover never buys past flat. Live refuses them.
  'short_limit_bid_offset',
  'cover_limit_ask_offset',
  'cover_market',
  'cover_pos',
] as const;

export type BotActionKind = (typeof BOT_ACTION_KINDS)[number];

export const BOT_ERROR_NEED_API_KEY =
  'Need Nova API key -- Desktop and Vite read the same repo NOVA_API_KEY, or save it here';
/** An older backend's refusal codes, said as what is true now: there is no Bot switch to turn on (ADR 072). */
export const BOT_ERROR_ARM_REQUIRED = 'The strategy bot is retired (ADR 072): the strategies only watch, and nothing was sent';
export const BOT_ERROR_NOT_ACTIVE = BOT_ERROR_ARM_REQUIRED;

/** In the backend's order (constants_bot.BOT_SETUPS): the six long setups with a scanner, the watch-only pullback
 * dip (#847), the five shorts (ADR 049), then the one without a scanner. */
export const BOT_SETUP_IDS = [
  'first_pullback',
  'bull_flag',
  'flat_top_breakout',
  'flat_top_5m',
  'red_to_green',
  'gap_and_go',
  'pullback_dip',
  'abcd',
  ...SHORT_SETUP_IDS,
  'micro_pullback',
] as const;


export const BOT_SETUP_LABELS: Record<string, string> = {
  first_pullback: 'First pullback',
  bull_flag: 'Bull flag',
  gap_and_go: 'Gap and Go',
  flat_top_breakout: 'Flat-top breakout',
  flat_top_5m: '5-minute flat top',
  red_to_green: 'Red to green',
  pullback_dip: 'Pullback dip',
  abcd: 'ABCD',
  micro_pullback: 'Micro pullback',
  ...SHORT_SETUP_LABELS,
};

/** The name as a tag beside a symbol (the Symbols card, the inbox, the Setups board). */
export const BOT_SETUP_SHORT: Record<string, string> = {
  first_pullback: 'First pullback',
  bull_flag: 'Bull flag',
  gap_and_go: 'Gap and Go',
  flat_top_breakout: 'Flat-top',
  flat_top_5m: '5m flat top',
  red_to_green: 'Red to green',
  pullback_dip: 'Dip',
  abcd: 'ABCD',
  micro_pullback: 'Micro pullback',
  ...SHORT_SETUP_TAGS,
};

/** A setup without a scanner says what is missing and what unblocks it (ADR 031 decision C). */
export const BOT_SETUP_NEXT: Record<string, { head: string; why: string; unblock: string }> = {
  micro_pullback: {
    head: 'Not watching: needs one-second bars',
    why: 'A micro pullback is a 1-2 candle dip inside a fast move. On one-minute bars it is invisible, and the scanners read one-minute bars.',
    unblock: 'The recorded tape building one-second bars (S5). Until then it has no rows, no score and no read-out, and says so.',
  },
};

/* The setup cards' rule lines and tape gate lines are built from the template in play
   (bot/templateFormat.ts, ADR 029), never written by hand. */

/** The right-click symbol menu (bot/BotSymbolMenu): the symbol once in the head, then one row per action. */
export const SYMBOL_MENU_CAPTION = 'Symbol actions';
export const SYMBOL_MENU_PIN_HINT = 'Keep this tab when you open another symbol';
export const SYMBOL_MENU_UNPIN_HINT = 'The next symbol you open may replace it';
export const SYMBOL_MENU_RECORD = 'Start recording';
export const SYMBOL_MENU_RECORD_HINT = 'Save its tape and Level 2 for Sim replay';
export const SYMBOL_MENU_STOP_RECORD = 'Hold to stop recording';
export const SYMBOL_MENU_REC_STATE = 'REC';

/* ---------- QA batch: orders / account / safety (2026-09-22) ---------- */
/** Endpoint names in "unreadable response" errors (botPayload.botUnreadableMessage). */
export const BOT_LABEL_SESSION = 'Bot session';
export const BOT_LABEL_AUDIT = 'Bot audit';

/* ---------- Kill switch (D-037, ADR 025, ADR 042 D) ---------- */
/** The one kill latch, in the words of what it does: on the desk it is "Freeze all orders" (ADR 044). */
export const KILL_SWITCH_TITLE = 'Freeze all orders';
export const KILL_SWITCH_TRIP_LABEL = 'Freeze all orders';
export const KILL_SWITCH_RESET_LABEL = 'Unfreeze orders';
export const KILL_SWITCH_TRIP_CONFIRM =
  'Freeze all orders? It cancels every working order on every venue but the stops that protect a position, and refuses every new order on every venue, a sell included, until you unfreeze. It sells nothing; Flatten and cancels still work.';
export const KILL_SWITCH_RESET_CONFIRM = 'Unfreeze orders? New orders will be allowed again.';
export const KILL_SWITCH_POLL_MS = 5000;
