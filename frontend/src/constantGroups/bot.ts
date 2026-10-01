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
] as const;

export type BotActionKind = (typeof BOT_ACTION_KINDS)[number];

/* ---------- The sleeve (ADR 042): one per venue, every Nova automatic buy ----------
   Fallback bounds for an API that sends no `caps_bounds` -- mirrors backend constants_bot.py. */
export const BOT_DEFAULT_MAX_SHARES = 1;
export const BOT_MAX_SHARES_CAP = 10;
export const BOT_BP_BUDGET_HARD_MAX_USD = 50;
export const BOT_BP_BUDGET_MIN_USD = 0.01;
export const BOT_BP_BUDGET_STEP_USD = 0.01;
export const BOT_DEFAULT_WORKING_TTL_SEC = 3;
export const BOT_WORKING_TTL_MIN_SEC = 1;
export const BOT_WORKING_TTL_MAX_SEC = 10;
/** Risk per trade (the sleeve's `risk_usd`): default and bounds when the API sends none. */
export const BOT_RISK_DEFAULT_USD = 20;
export const BOT_RISK_MIN_USD = 1;
export const BOT_RISK_MAX_USD = 10_000;
/** The slider stops here; the backend's bound may be higher (typed values still go through it). */
export const BOT_RISK_SLIDER_MAX_USD = 500;
/** Nova's automatic entries a day per venue (bot + Auto-entry): bounds when the API sends none. */
export const BOT_ENTRIES_PER_DAY_MIN = 1;
export const BOT_ENTRIES_PER_DAY_MAX = 3;
/** The loss breakers' defaults: a venue the operator never moved reads these (ADR 032). */
export const BOT_SOFT_BREAKER_USD = -50;
export const BOT_HARD_BREAKER_USD = -200;
/** ADR 032 bounds, [loosest, tightest] -- mirrors backend/constants_bot.py (the backend checks again). */
export const BOT_BREAKER_SOFT_BOUNDS: readonly [number, number] = [-1000, -5];
export const BOT_BREAKER_HARD_BOUNDS: readonly [number, number] = [-5000, -10];
export const BOT_BREAKER_STEP_USD = 5;

export const BOT_LEVEL_FIELD_LABEL = 'Master level';
export const BOT_LEVEL_LABELS = {
  0: 'Off',
  1: 'Eyes',
  2: 'Strategy',
} as const;
/** The master ceiling (ADR 042): the most any setup may do on this venue. */
export const BOT_LEVEL_HINTS = {
  0: 'Off -- the most any setup may do on this venue is nothing: no proposal, no trade; every scanner still watches and scores in silence. The localhost bot API is dark.',
  1: 'Eyes -- the most any setup may do on this venue is propose (near + go): you place. Nova\'s bot trades nothing.',
  2: 'Strategy -- the most any setup may do on this venue: setups at Strategy may be traded by Nova\'s bot after Activate (Paper and Sim only); setups at Eyes propose.',
} as const;
export const BOT_STATE_ACTIVE = 'Active';
export const BOT_STATE_NOT_ACTIVE = 'Not active';
export const BOT_ACTIVATE_LABEL = 'Activate';
export const BOT_DEACTIVATE_LABEL = 'Deactivate';
export const BOT_API_KEY_HINT = 'Need Nova API key to change the bot';
export const BOT_API_KEY_SAVE = 'Save';
export const BOT_ERROR_NEED_API_KEY =
  'Need Nova API key -- Desktop and Vite read the same repo NOVA_API_KEY, or save it here';
export const BOT_ERROR_ARM_REQUIRED = 'The bot is not active -- press Activate on the Bots page first';
export const BOT_ERROR_NOT_ACTIVE = 'Not active -- press Activate on the Bots page first';

/* ---------- The playbook (ADR 027): the operator's setups ---------- */
/** Mirrors backend/constants_bot.py BOT_SETUPS. */
export const BOT_SETUP_FIRST_PULLBACK = 'first_pullback';
/** In the backend's order (constants_bot.BOT_SETUPS): the four with a scanner first. */
export const BOT_SETUP_IDS = [
  'first_pullback',
  'bull_flag',
  'flat_top_breakout',
  'red_to_green',
  'gap_and_go',
  'micro_pullback',
] as const;
export type BotSetupId = (typeof BOT_SETUP_IDS)[number];

export const BOT_SETUP_LABELS: Record<string, string> = {
  first_pullback: 'First pullback',
  bull_flag: 'Bull flag',
  gap_and_go: 'Gap and Go',
  flat_top_breakout: 'Flat-top breakout',
  red_to_green: 'Red to green',
  micro_pullback: 'Micro pullback',
};

/** The name as a tag beside a symbol (the Symbols card, the inbox, the Setups board). */
export const BOT_SETUP_SHORT: Record<string, string> = {
  first_pullback: 'First pullback',
  bull_flag: 'Bull flag',
  gap_and_go: 'Gap and Go',
  flat_top_breakout: 'Flat-top',
  red_to_green: 'Red to green',
  micro_pullback: 'Micro pullback',
};

/** One line on what each setup trades. */
export const BOT_SETUP_BLURBS: Record<string, string> = {
  first_pullback: 'The first 1-3 candle dip after a 5%+ leg to a new high, bought over the pullback high.',
  bull_flag: 'A pole of 3+ green candles on rising volume, then 2-3 quiet red candles that hold the 9 EMA — bought over the flag.',
  gap_and_go: 'Buy the break of the pre-market high on a gapper at the open.',
  flat_top_breakout: '2-6 tight candles just under the high of day, then a green candle that holds the break.',
  red_to_green: 'Trades below the 09:30 open, then back through it — buy the reclaim, one try a day.',
  micro_pullback: 'A 1-2 candle dip inside a fast move, read on seconds.',
};

/**
 * What the research said about each setup on bars alone (Bot-Trading-Plan):
 * the verdict badge, the whole line, and the detail the card prints after the badge.
 */
export const BOT_SETUP_RESEARCH: Record<string, { verdict: 'failed' | 'not_tested' | 'testing'; text: string; detail: string }> = {
  first_pullback: {
    verdict: 'failed',
    text: 'Bars alone (P1): -0.30R. Live with the tape gate: the read-out measures it.',
    detail: '−0.30R (P1): the tape gate is what is being tested',
  },
  bull_flag: {
    verdict: 'not_tested',
    text: 'Never tested on bars: its read-out is its first test (rules pre-registered in ADR 031).',
    detail: 'its read-out is its first test (rules pre-registered, ADR 031)',
  },
  gap_and_go: {
    verdict: 'failed',
    text: 'Bars alone: failed -- dies on a few cents of slippage (A2).',
    detail: 'dies on a few cents of slippage (A2)',
  },
  flat_top_breakout: {
    verdict: 'failed', text: 'Bars alone: failed, -0.83R on 63 trades (P2).', detail: '−0.83R on 63 trades (P2)',
  },
  red_to_green: {
    verdict: 'failed', text: 'Bars alone: failed, -0.22R on 398 trades (P3).', detail: '−0.22R on 398 trades (P3)',
  },
  micro_pullback: {
    verdict: 'not_tested', text: 'Not tested -- planned on one-second bars (S5).', detail: 'planned on one-second bars (S5)',
  },
};

/** A setup without a scanner says what is missing and what unblocks it (ADR 031 decision C). */
export const BOT_SETUP_NEXT: Record<string, { head: string; why: string; unblock: string }> = {
  gap_and_go: {
    head: 'Not watching: no scanner yet · it is next',
    why: 'Gap and Go buys the break of the pre-market high. Nothing on the desk tracks each gapper\'s pre-market high as a level yet, so no scanner can arm it.',
    unblock: 'A pre-market-high detector on the same lanes and tape gate as the others (ADR 031: next after these three).',
  },
  micro_pullback: {
    head: 'Not watching: needs one-second bars',
    why: 'A micro pullback is a 1-2 candle dip inside a fast move. On one-minute bars it is invisible, and the scanners read one-minute bars.',
    unblock: 'The recorded tape building one-second bars (S5). Until then it has no rows, no score and no read-out, and says so.',
  },
};

/* The setup cards' rule lines and tape gate lines are built from the template in play
   (bot/templateFormat.ts, ADR 029), never written by hand. */

export const BOT_NO_SCANNER_TITLE = 'No scanner yet -- it cannot watch, propose or trade until it has one';

/** The setups this build has a scanner for -- mirrors backend constants_bot.BOT_SCANNER_SETUPS (ADR 031). */
export const BOT_SCANNER_SETUP_IDS: readonly string[] = ['first_pullback', 'bull_flag', 'flat_top_breakout', 'red_to_green'];
/* A backend older than ADR 031 runs the first pullback only. The page says the backend needs a
   reload -- never "No scanner yet", which would say the feature is missing when it is not loaded. */
export const BOT_STALE_BACKEND_BANNER =
  'Your backend is still running code from before the setup scanners, so only the first pullback is running. '
  + 'Reload it to start the bull flag, flat-top and red to green scanners and to move the loss breakers. '
  + 'A reload takes about half a minute, and a recording picks up where it left off.';
export const BOT_STALE_BACKEND_STATUS = 'Not running yet: the backend needs a reload to start this scanner';
export const BOT_STALE_BACKEND_WHY =
  'The backend is running code from before this scanner -- reload it (gear, Reload backend) to start it';
export const BOT_STALE_BACKEND_TEMPLATE = 'needs a backend reload';

/* ---------- The levels (ADR 042) ----------
   The hero's dial is the master ceiling: the most any setup may do on this venue. Each
   setup card has its own Off / Eyes / Strategy; what a setup may do now is the lower of
   the two. Off watches and scores in silence; Eyes proposes on near + go; Strategy lets
   Nova's bot trade its go triggers on Paper and Sim once Activate is pressed -- until
   then it proposes like Eyes. There is no chosen setup any more. */
export const BOT_LEVEL_BLURBS = {
  0: 'Nothing proposes or trades · every scanner scores in silence',
  1: 'Setups may propose · you place',
  2: 'Setups at Strategy may trade after Activate (Paper, Sim)',
} as const;

/** What each level means on a setup card's own switch (ADR 042). */
export const BOT_SETUP_LEVEL_TIPS = {
  0: 'Off: this setup\'s scanner still watches every HOD Momo name and scores each armed setup on the scoreboard, so its read-out keeps collecting — but it never proposes or trades: no ping, no inbox card, no staged ticket.',
  1: 'Eyes: when a setup comes near its trigger and the tape reads GO, it proposes — a ping, a card in the inbox and on every tab, a staged ticket at most. You press Place. Any number of setups can be at Eyes.',
  2: 'Strategy: once you press Activate, Nova\'s bot may trade this setup\'s GO triggers on the stocks set to Bot, on Paper and Sim — the first trigger wins, one trade at a time, inside its bot window and the daily cap. While the bot is not active it proposes like Eyes. Any number of setups can be at Strategy; the master level caps them all. Live trading by a bot is not built.',
} as const;
export const BOT_SETUP_LEVEL_CHIPS = {
  0: 'Off · scores silently',
  1: 'Eyes · pings on near + go',
  2: 'Strategy · the bot may trade it',
} as const;
/** At Strategy while the bot is not active: it proposes like Eyes until Activate. */
export const BOT_SETUP_LEVEL_CHIP_WAITING = 'Strategy · proposes until Activate';
export const BOT_SETUP_LEVEL_WAITING_TIP =
  'This setup is at Strategy, but the bot is not active on this venue, so it proposes like Eyes. Press Activate on the hero and the bot may trade its GO triggers.';
/** A setup's own level is above the master's: what it may do now is the master's. */
export const botSetupCapped = (own: string, effective: string): string => `${own} · capped to ${effective} by the bot's level`;
export const BOT_SETUP_CAPPED_TIP =
  'The master level on the hero is the most any setup may do on this venue. This setup\'s own switch is higher, so it acts at the master level until you raise it.';

/* ---------- Gates (backend bot/gates.py, ADR 042) ---------- */
/** Gate ids, in the order the page lists them. */
export const BOT_GATE_LABELS: Record<string, string> = {
  venue: 'Venue',
  level: 'Master level',
  setups: 'Setups at Strategy',
  padlock: 'Padlock',
  allowlist: 'Bot stocks',
  depth_lines: 'Depth line',
  bot_trip: 'Bot trip',
  day_lock: 'Day lock',
  kill_switch: 'Kill switch',
  window: 'Bot window',
  daily_cap: 'Daily cap',
  extended_hours: 'Hours',
  commissions: 'Commissions',
};
/** What each gate checks, on its chip's hover. */
export const BOT_GATE_TIPS: Record<string, string> = {
  venue: 'Nova\'s bot trades Paper, and Sim at the live edge (the playhead on the wall clock). Live trading by a bot is not built, and a Sim replay is the past, so the bot never trades there. Activate needs this.',
  level: 'The master level (the dial beside these chips) is the most any setup may do on this venue. The bot trades only at Strategy. Activate needs this.',
  setups: 'At least one setup card set to Strategy (its own switch, under the master level). The bot plays only those setups\' GO triggers. Activate needs this.',
  padlock: 'The desk padlock (spend arming). It is locked at every start and when anyone locks it, and locking it turns the bot off. While locked nothing places an order. Activate needs this.',
  allowlist: 'The stocks set to Bot (Nova buys and sells) on this venue, under Who trades. The bot trades nothing else; the scanners and Eyes still watch every HOD Momo name. Activate needs at least one.',
  depth_lines: 'Nova must hold a stock\'s Level 2 line to read its tape at the trigger (IBKR allows 3 at once). This is open while one bot stock has a line; a trigger on a stock without one is skipped, and the activity says so. Checked on every order.',
  bot_trip: 'The soft loss breaker: when this venue\'s day P&L falls to its bot trip, Nova flattens and turns the bot off. Activate re-enables it for today after you confirm; it clears by itself at 04:00 ET.',
  day_lock: 'The hard loss breaker on this venue: the all-stop flattened the account and locks bot and manual buys on this venue until 04:00 ET. Flatten and cancel still work. Checked on every order.',
  kill_switch: 'The kill switch cancels every working order on every venue and refuses new buys on every venue until you reset it. Checked on every order.',
  window: 'Each setup\'s bot window, from its template and inside its arming window: the bot buys only a trigger inside it. Open while any setup at Strategy is inside its window now. Checked on every order.',
  daily_cap: 'One count for Nova\'s automatic entries (the bot and Auto-entry) on this venue today, from the sleeve\'s "Nova entries a day". A missed entry gives the day back; Approve is yours and is counted, never capped. Checked on every order.',
  extended_hours: 'Outside 09:30–16:00 ET the bot and Auto-entry buy only when the sleeve allows extended hours. Checked on every order.',
  commissions: 'Live\'s day P&L needs its commissions; while they cannot be read, new entries wait (#564). Checked on every order.',
};
/** #564: the Live day P&L cannot read its commissions, so new bot entries wait. */
export const BOT_GATE_COMMISSIONS_HELD = 'Commissions unreadable — Live entries held until they read';

/* ---------- Read-outs (Bot-Trading-Plan §2g, ADR 042 G) ---------- */
export const BOT_READOUT_TITLE = 'Read-out';
export const BOT_READOUT_STATE_LABELS: Record<string, string> = {
  collecting: 'Collecting',
  passed: 'Passed',
  not_passed: 'Not passed yet',
  failed: 'Failed',
  unavailable: 'Scoreboard not open',
};
/** What a read-out is, on every setup card (ADR 042 G): what it measures and what it does not unlock. */
export const BOT_READOUT_WHAT =
  'Measures whether the tape gate turns this setup into a winner. Nova\'s bot trades Paper and Sim only; '
  + 'Live trading by a bot is not built, so passing it unlocks nothing yet.';
/** How it scores, against how the bot trades (ADR 042 G). */
export const BOT_READOUT_EXITS =
  'It scores the backtest\'s exit (half at target 1, the stop to break-even, a 9 EMA trail); '
  + 'the bot sells everything at target 1, with a 15-minute time stop.';
/** The read-out's hover: what it measures, what it does not unlock, and how it scores. */
export const BOT_READOUT_TIP = (setup: string): string =>
  `${BOT_READOUT_WHAT}\n`
  + `It counts every ${setup} this template armed that triggered, split by what the tape said at the trigger. `
  + 'GO: the tape said go. Blind / wait: Nova held no Level 2 line, or the tape said wait — the control group.\n'
  + 'It passes at 50 go setups whose average net R (after a cent of slippage each way) is above +0.2 and above the control\'s, '
  + 'judged on the first 100 go setups; 100 without a pass is failed.\n'
  + 'It scores the backtest\'s exit — half at target 1, the stop to break-even, the rest on a 9 EMA trail — '
  + 'while Nova\'s bot sells everything at target 1, with a 15-minute time stop. Its triggers outside the bot\'s window count here, '
  + 'though the bot would never have bought them.';
export const botReadoutInside = (triggered: number, go: number, start: string, end: string): string =>
  `${triggered} triggered inside the bot window ${start}–${end} (${go} at GO)`;

export const BOT_DESK_ARM_HEADER = 'X-Nova-Desk-Arm';
export const BOT_DESK_ARM_STORAGE = 'nova_bot_desk_arm';

/* ---------- The bot's stocks (ADR 042 F): set per stock, one owner ----------
   Adding a stock to the bot sets it to Bot (Nova buys and sells) through the
   stock-mode rules; a refusal is shown in the backend's own words. */
export const botTradeAddLabel = (symbol: string): string => `Let the bot trade ${symbol} (Nova buys and sells)`;
export const botTradeRemoveLabel = (symbol: string): string => `Stop the bot trading ${symbol}`;
export const BOT_ALLOWLIST_ADD = 'Let the bot trade this stock (Nova buys and sells)';
export const BOT_ALLOWLIST_REMOVE = 'Stop the bot trading this stock';
export const botTradeRefusedTitle = (symbol: string, add: boolean): string =>
  (add ? `The bot cannot trade ${symbol}` : `${symbol} stays with the bot`);

/** The right-click symbol menu (bot/BotSymbolMenu): the symbol once in the head, then one row per action. */
export const SYMBOL_MENU_CAPTION = 'Symbol actions';
export const SYMBOL_MENU_PIN_HINT = 'Keep this tab when you open another symbol';
export const SYMBOL_MENU_UNPIN_HINT = 'The next symbol you open may replace it';
export const SYMBOL_MENU_WATCH_HINT = 'Toast when it hits HOD Momo, runs up, or a setup forms';
export const SYMBOL_MENU_UNWATCH_HINT = 'Stop its toasts';
export const SYMBOL_MENU_WATCH_STATE = 'Watching';
export const SYMBOL_MENU_RECORD = 'Start recording';
export const SYMBOL_MENU_RECORD_HINT = 'Save its tape and Level 2 for Sim replay';
export const SYMBOL_MENU_STOP_RECORD = 'Hold to stop recording';
export const SYMBOL_MENU_REC_STATE = 'REC';
export const SYMBOL_MENU_ALLOW_HINT = 'Sets it to Bot under Who trades: Nova\'s bot may buy it and sell it on this venue';
export const SYMBOL_MENU_UNALLOW_HINT = 'Back to Signal only: Nova stops buying it (an open trade keeps its exits)';
export const SYMBOL_MENU_ALLOW_STATE = 'Bot';
export const SYMBOL_MENU_BOT_BUSY_WHY = 'Asking Nova -- wait for the answer';
export const BOT_ALLOWLIST_HINT =
  'The stocks Nova\'s bot may trade on this venue (Nova buys and sells). Right-click a scanner row, Trader tab or chart, or set Bot under Who trades. An empty list: the bot trades nothing.';
export const BOT_ALLOWLIST_EMPTY = 'none -- the bot trades nothing';
export const BOT_ALLOWLIST_ADD_LABEL = 'Add a stock';
export const BOT_ALLOWLIST_ADD_BUTTON = 'Add';
export const BOT_ALLOWLIST_CHIP_REMOVE = 'Remove';
/** Mirrors backend/constants_bot.py -- the bot's stocks, not the sleeve's order kinds. */
export const BOT_SYMBOL_ALLOWLIST_CAP = 50;
export const BOT_ALLOWLIST_STRIP_LABEL = 'Bot stocks';
export const BOT_ALLOWLIST_STRIP_TITLE = 'The stocks the bot may trade';

export function botAllowlistStripLabel(count: number): string {
  return `${BOT_ALLOWLIST_STRIP_LABEL} · ${count}`;
}

/* ---------- Loss breakers (ADR 032, ADR 042 D): per venue, one day boundary at 04:00 ET ---------- */
export const BOT_BREAKER_SOFT_LABEL = 'Bot trip';
export const BOT_BREAKER_HARD_LABEL = 'All-stop';
export const BOT_BREAKER_HINT =
  'Drag either marker to move it. Each venue keeps its own pair, saved in the bot session, so a restart keeps them. The bot trip flattens this venue and turns the bot off; the all-stop flattens and locks bot and manual buys on this venue until 04:00 ET. A Sim replay compares nothing: its P&L is not today\'s.';
export const BOT_BREAKER_SOFT_TIP =
  'Bot trip: when this venue\'s day P&L falls to this, Nova flattens and turns the bot off. The desk can still trade; Activate re-enables the bot for today after you confirm, and it clears at 04:00 ET.\nDrag to move it (in $5 steps). It always sits above the all-stop.';
export const BOT_BREAKER_HARD_TIP =
  'All-stop: when this venue\'s day P&L falls to this, Nova flattens and locks bot and manual buys on this venue until 04:00 ET. Flatten and cancel still work.\nDrag to move it (in $5 steps). It always sits below the bot trip.';
export const BOT_BREAKER_NOW_TIP =
  'This venue\'s day P&L for the whole account — the figure both breakers compare. On Live it is after commissions.';
/** Moving a breaker never undoes one that fired (ADR 032). */
export const BOT_BREAKER_FIRED_NOTE = 'Moving a breaker never clears one that already fired.';
export const BOT_BREAKER_LOOSEN_LIVE = (which: string, from: string, to: string): string =>
  `Loosen Live's ${which} from ${from} to ${to}? Real money: the account can lose more before Nova steps in. The change is saved and recorded on the bot audit.`;
export const BOT_BREAKER_LOOSEN_LIVE_OK = 'Loosen Live';

/* ---------- QA batch: orders / account / safety (2026-09-22) ---------- */
/** Endpoint names in "unreadable response" errors (botPayload.botUnreadableMessage). */
export const BOT_LABEL_SESSION = 'Bot session';
export const BOT_LABEL_PROPOSALS = 'Bot proposals';
export const BOT_LABEL_AUDIT = 'Bot audit';

/* ---------- Kill switch (D-037, ADR 025, ADR 042 D) ---------- */
/** The one kill latch, in the words of what it does. */
export const KILL_SWITCH_TITLE = 'Kill switch';
export const KILL_SWITCH_HINT =
  'Cancels every working order on every venue and blocks new buys on every venue until you reset it. It does not sell positions — Flatten and cancel still work, and every other new order waits too. It stays on across a restart until you reset it here. The red KILL at the top of the desk is separate: it turns the bot off, locks the padlock, cancels and flattens this venue.';
export const KILL_SWITCH_TRIP_LABEL = 'Kill switch';
export const KILL_SWITCH_RESET_LABEL = 'Reset kill switch';
export const KILL_SWITCH_TRIP_CONFIRM =
  'Trip the kill switch? It cancels every working order on every venue and blocks new buys on every venue until you reset it. It does not sell positions.';
export const KILL_SWITCH_RESET_CONFIRM = 'Reset the kill switch? New orders will be allowed again.';
export const KILL_SWITCH_POLL_MS = 5000;
