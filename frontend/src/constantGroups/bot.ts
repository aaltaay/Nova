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

export const BOT_DEFAULT_MAX_SHARES = 1;
export const BOT_MAX_SHARES_CAP = 10;
export const BOT_BP_BUDGET_HARD_MAX_USD = 50;
export const BOT_BP_BUDGET_MIN_USD = 0.01;
export const BOT_BP_BUDGET_STEP_USD = 0.01;
export const BOT_DEFAULT_WORKING_TTL_SEC = 3;
export const BOT_WORKING_TTL_MIN_SEC = 1;
export const BOT_WORKING_TTL_MAX_SEC = 10;
export const BOT_ADVISE_DEFAULT_USD_CAP = 2;
export const BOT_ADVISE_DEFAULT_CALL_CAP = 10;
/** The loss breakers' defaults: a venue the operator never moved reads these (ADR 032). */
export const BOT_SOFT_BREAKER_USD = -50;
export const BOT_HARD_BREAKER_USD = -200;
/** ADR 032 bounds, [loosest, tightest] -- mirrors backend/constants_bot.py (the backend checks again). */
export const BOT_BREAKER_SOFT_BOUNDS: readonly [number, number] = [-1000, -5];
export const BOT_BREAKER_HARD_BOUNDS: readonly [number, number] = [-5000, -10];
export const BOT_BREAKER_STEP_USD = 5;

export const BOT_AUTONOMY_LABEL = 'Bot Autonomy';
export const BOT_LEVEL_FIELD_LABEL = 'Level';
export const BOT_LEVEL_LABELS = {
  0: 'Off',
  1: 'Eyes',
  2: 'Strategy',
} as const;
export const BOT_LEVEL_HINTS = {
  0: 'L0 Off -- bot API dark; the chosen setup is watched and scored in silence, no proposals',
  1: 'L1 Eyes -- the chosen setup proposes on near + go, and a connected bot may watch and propose; you place',
  2: 'L2 Strategy -- after Activate the bot trades the chosen setup itself on Paper and Sim; Live waits on its read-out',
} as const;
export const BOT_STATE_ACTIVE = 'Active';
export const BOT_STATE_NOT_ACTIVE = 'Not active';
export const BOT_ACTIVATE_LABEL = 'Activate';
export const BOT_DEACTIVATE_LABEL = 'Deactivate';
export const BOT_API_KEY_HINT = 'Need Nova API key to change Bot Autonomy';
export const BOT_API_KEY_SAVE = 'Save';
export const BOT_ERROR_NEED_API_KEY =
  'Need Nova API key -- Desktop and Vite read the same repo NOVA_API_KEY, or save it here';
export const BOT_ERROR_ARM_REQUIRED = 'Activate first, then choose Strategy';
export const BOT_ERROR_NOT_ACTIVE = 'Not active -- Activate before live fire';

/* ---------- The playbook (ADR 027): the operator's setups ---------- */
/** Mirrors backend/constants_bot.py BOT_SETUPS; only a setup with a scanner can play. */
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
export const BOT_SETUP_FIELD_LABEL = 'Setup';

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
    text: 'Bars alone (P1): -0.30R. Live with the tape gate: the read-out decides.',
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

/** The one setup Nova's bot trades by itself at Strategy; every other setup keeps scanning. */
export const BOT_CHOSEN_BADGE = 'Bot trades this';
export const BOT_NO_SCANNER_TITLE = 'No scanner yet -- it cannot play until it has one and its read-out passes';

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

/* ---------- The Bots page hero (ADR 027, ADR 030, ADR 031) ----------
   The hero's level is the chosen setup's. Off: the bot API is dark and the chosen
   setup is watched and scored in silence (decision A). Eyes: it proposes on near +
   go, and a bot on the localhost bot API (ADR 016) may watch and propose. Strategy,
   after Activate: Nova's own bot trades the chosen setup on Paper and Sim (ADR
   030); Live waits on that setup's read-out. Every other setup has its own Off /
   Eyes on its card. */
export const BOT_STRATEGY_PLAYS = 'The bot trades the chosen setup itself on Paper and Sim; Live waits on its read-out';
export const BOT_LEVEL_BLURBS = {
  0: 'Bot API dark · the chosen setup scores in silence',
  1: 'Proposes on near + go · you place',
  2: 'The bot trades the chosen setup on Paper and Sim · Live waits on its read-out',
} as const;

/** What each level means on a setup card's own switch (ADR 031 decisions A and B). */
export const BOT_SETUP_LEVEL_TIPS = {
  0: 'Off: this setup\'s scanner still watches every HOD Momo name and scores each armed setup on the scoreboard, so its read-out keeps collecting — but it never proposes: no ping, no inbox card, no staged ticket.',
  1: 'Eyes: when a setup comes near its trigger and the tape reads GO, it proposes — a ping, a card in the inbox and on every tab, a staged ticket at most. You press Place. Several setups can be at Eyes at once.',
  2: 'Strategy: after Activate, Nova\'s own bot trades this setup by itself on Paper and Sim — one trade a day inside its window, under every gate. Live waits on this setup\'s read-out. Only the chosen setup can be here.',
} as const;
export const BOT_SETUP_LEVEL_CHIPS = {
  0: 'Off · scores silently',
  1: 'Eyes · pings on near + go',
  2: 'Strategy · the bot trades it',
} as const;
/** Why a setup's Strategy segment is locked. */
export const BOT_SETUP_STRATEGY_WHY = 'Only the chosen setup can be at Strategy -- choose this one first (its radio), then pick Strategy';

/** Gate ids from backend/bot/gates.py, in the order the page lists them. */
export const BOT_GATE_LABELS: Record<string, string> = {
  level: 'Level',
  allowlist: 'Allowlist',
  desk_armed: 'Desk armed',
  depth_lines: 'Depth lines',
  readout: 'Read-out',
  bot_trip: 'Bot trip clear',
  day_lock: 'No day lock',
  kill_switch: 'Kill switch off',
  window: 'Window',
  commissions: 'Commissions read',
};
/** #564: the Live day P&L cannot read its commissions, so new bot entries wait. */
export const BOT_GATE_COMMISSIONS_HELD = 'Commissions unreadable — Live entries held until they read';

export const BOT_READOUT_TITLE = 'Read-out to unlock Strategy on Live';
/** ADR 030: the read-out gates Live only. */
export const BOT_READOUT_WAIVED_NOTE = 'Paper and Sim do not wait on it — the bot trades there now. Live does.';
export const BOT_READOUT_STATE_LABELS: Record<string, string> = {
  collecting: 'Collecting',
  passed: 'Passed',
  not_passed: 'Not passed yet',
  failed: 'Failed',
  unavailable: 'Scoreboard not open',
};
export const BOT_READOUT_RULE =
  'Needs 50 go setups triggered, average net R above +0.2 and above blind / wait. Judged on the first 100.';
/** The read-out's hover: what it counts and why it matters, per setup. */
export const BOT_READOUT_TIP = (setup: string): string =>
  `The read-out counts every ${setup} this scanner armed that triggered, split by what the tape said at the trigger.\n`
  + 'GO: the tape said go. Blind / wait: Nova held no Level 2 line, or the tape said wait — the control group.\n'
  + 'It passes at 50 go setups whose average net R (after a cent of slippage each way) is above +0.2 and above the control\'s. '
  + 'It is judged on the first 100 go setups; 100 without a pass is failed.\n'
  + 'Passing is what lets this setup trade at Strategy on Live. Paper and Sim do not wait on it.';
export const BOT_ERROR_READOUT = 'Strategy waits on the chosen setup\'s read-out';

export const BOT_DESK_ARM_HEADER = 'X-Nova-Desk-Arm';
export const BOT_DESK_ARM_STORAGE = 'nova_bot_desk_arm';
export const BOT_ALLOWLIST_ADD = 'Add to bot allowlist';
export const BOT_ALLOWLIST_REMOVE = 'Remove from bot allowlist';

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
export const SYMBOL_MENU_ALLOW_HINT = 'Let the bot act on this symbol';
export const SYMBOL_MENU_UNALLOW_HINT = 'The bot stops acting on it';
export const SYMBOL_MENU_ALLOW_STATE = 'On';
export const BOT_ALLOWLIST_HINT =
  'Right-click a scanner row, trader tab, or chart to add or remove. Empty list is fail-closed.';
export const BOT_ALLOWLIST_EMPTY = 'empty -- fail closed';
export const BOT_ALLOWLIST_ADD_LABEL = 'Add ticker';
export const BOT_ALLOWLIST_ADD_BUTTON = 'Add';
export const BOT_ALLOWLIST_CHIP_REMOVE = 'Remove';
/** Mirrors backend/constants_bot.py -- session.symbol_allowlist only, not caps.allowlist. */
export const BOT_SYMBOL_ALLOWLIST_CAP = 50;
export const BOT_ALLOWLIST_STRIP_LABEL = 'Allowlist';
export const BOT_ALLOWLIST_STRIP_TITLE = 'Symbol allowlist';

export function botAllowlistStripLabel(count: number): string {
  return `${BOT_ALLOWLIST_STRIP_LABEL} · ${count}`;
}
export const BOT_BREAKER_SOFT_LABEL = 'Bot trip';
export const BOT_BREAKER_HARD_LABEL = 'All-stop';
export const BOT_BREAKER_HINT =
  'Drag either marker to move it. Each venue keeps its own pair, saved in the bot session, so a restart keeps them. The bot trip flattens and drops the bot to L0; the all-stop flattens and locks bot and manual buys until the next ET midnight.';
export const BOT_BREAKER_SOFT_TIP =
  'Bot trip: when the whole account\'s day P&L on this venue falls to this, Nova flattens and drops the bot to L0. The desk can still trade; Activate re-enables the bot the same day.\nDrag to move it (in $5 steps). It always sits above the all-stop.';
export const BOT_BREAKER_HARD_TIP =
  'All-stop: when the day P&L falls to this, Nova flattens and locks bot and manual buys until the next ET midnight. Flatten and kill still work.\nDrag to move it (in $5 steps). It always sits below the bot trip.';
export const BOT_BREAKER_NOW_TIP =
  'Today\'s day P&L for the whole account on this venue — the figure both breakers compare. On Live it is after commissions.';
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

/* ---------- Kill switch (D-037, ADR 025) ---------- */
/** The one kill latch: every new order from every source is refused until reset. */
export const KILL_SWITCH_TITLE = 'Kill switch';
export const KILL_SWITCH_HINT =
  'Stops every new order from every source -- you, hotkeys and the bot -- and cancels everything working. Flatten and cancel still work. It stays on across a restart until you reset it here. The red KILL button at the top of the desk is separate: it drops the bot to L0, locks the desk, cancels and flattens.';
export const KILL_SWITCH_CLEAR = 'Off -- orders can be placed';
export const KILL_SWITCH_TRIPPED = 'TRIPPED -- every new order is refused';
export const KILL_SWITCH_UNKNOWN = 'Unknown -- the kill switch did not answer';
export const KILL_SWITCH_TRIP_LABEL = 'Stop all orders';
export const KILL_SWITCH_RESET_LABEL = 'Reset kill switch';
export const KILL_SWITCH_TRIP_CONFIRM =
  'Trip the kill switch? Every new order is refused until you reset it, and every working order is cancelled.';
export const KILL_SWITCH_RESET_CONFIRM = 'Reset the kill switch? New orders will be allowed again.';
export const KILL_SWITCH_POLL_MS = 5000;
