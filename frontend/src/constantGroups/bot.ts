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
export const BOT_SOFT_BREAKER_USD = -50;
export const BOT_HARD_BREAKER_USD = -200;

export const BOT_AUTONOMY_LABEL = 'Bot Autonomy';
export const BOT_LEVEL_FIELD_LABEL = 'Level';
export const BOT_LEVEL_LABELS = {
  0: 'Off',
  1: 'Eyes',
  2: 'Strategy',
} as const;
export const BOT_LEVEL_HINTS = {
  0: 'L0 dark -- no watch, propose, or writes',
  1: 'L1 Eyes -- watch and propose; human places',
  2: 'L2 Strategy -- live under gates after Activate',
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
export const BOT_SETUP_IDS = [
  'first_pullback',
  'gap_and_go',
  'flat_top_breakout',
  'red_to_green',
  'micro_pullback',
] as const;
export type BotSetupId = (typeof BOT_SETUP_IDS)[number];
export const BOT_SETUP_FIELD_LABEL = 'Setup';

export const BOT_SETUP_LABELS: Record<string, string> = {
  first_pullback: 'First pullback',
  gap_and_go: 'Gap and Go',
  flat_top_breakout: 'Flat-top breakout',
  red_to_green: 'Red to green',
  micro_pullback: 'Micro pullback',
};

/** One line on what each setup trades. */
export const BOT_SETUP_BLURBS: Record<string, string> = {
  first_pullback: 'The first 1-3 candle dip after a 5%+ leg to a new high, bought over the pullback high.',
  gap_and_go: 'Buy the break of the pre-market high on a gapper at the open.',
  flat_top_breakout: '2-6 tight candles just under the high of day, then the break.',
  red_to_green: 'Trades below the open, then back through it -- buy the reclaim.',
  micro_pullback: 'A 1-2 candle dip inside a fast move, read on seconds.',
};

/** What the research said about each setup on bars alone (Bot-Trading-Plan). */
export const BOT_SETUP_RESEARCH: Record<string, { verdict: 'failed' | 'not_tested' | 'testing'; text: string }> = {
  first_pullback: { verdict: 'failed', text: 'Bars alone (P1): -0.30R. Live with the tape gate: the read-out decides.' },
  gap_and_go: { verdict: 'failed', text: 'Bars alone: failed -- dies on a few cents of slippage (A2).' },
  flat_top_breakout: { verdict: 'failed', text: 'Bars alone: failed, -0.83R on 63 trades (P2).' },
  red_to_green: { verdict: 'failed', text: 'Bars alone: failed, -0.22R on 398 trades (P3).' },
  micro_pullback: { verdict: 'not_tested', text: 'Not tested -- planned on one-second bars (S5).' },
};

export const BOT_SETUP_NEXT: Record<string, string> = {
  gap_and_go: 'No scanner yet · next: a pre-market-high detector + the same tape gate',
  flat_top_breakout: 'No scanner yet · could reuse the first-pullback detector',
  red_to_green: 'No scanner yet',
  micro_pullback: 'No scanner yet',
};

/** The chosen setup's rules card (first pullback, Bot-Trading-Plan §3). */
export const BOT_FIRST_PULLBACK_RULES: ReadonlyArray<readonly [string, string]> = [
  ['Stock', 'Leading gainer · Five Pillars · $3-10 · float < 10M'],
  ['Setup', 'Leg >= 5% to a new high · 1-3 red candles hold the 9 EMA and half the leg'],
  ['Entry', "Over the last pullback candle's high (+1c) -- only when the tape says GO"],
  ['Trade', '07:00-10:00 · one a day · fixed size · 20c target · 20c max loss'],
];

export const BOT_TAPE_GATE_LINES: ReadonlyArray<readonly [string, string]> = [
  ['go', 'green prints, nothing holding the level'],
  ['wait', '25k+ seller not thinning'],
  ['veto', 'wide spread / 100k+ seller'],
  ['blind', 'no Level 2'],
];

export const BOT_ADD_SETUP_TITLE = 'Add a setup from your catalogue';
export const BOT_ADD_SETUP_HINT =
  'The full list is on your desk PC (F:). Each one lands here with its rules, a backtest and a scanner.';
export const BOT_STRATEGIES_TITLE = 'Strategies from your Warrior Trading material';
export const BOT_STRATEGIES_SUB = 'one setup plays at a time';
export const BOT_CHOSEN_BADGE = 'Chosen';
export const BOT_NO_SCANNER_TITLE = 'No scanner yet -- it cannot play until it has one and its read-out passes';

/* ---------- The Bots page hero (ADR 027) ---------- */
export const BOT_LEVEL_BLURBS = {
  0: 'Dark -- no watching, no proposals',
  1: 'Watches your setups and proposes -- you place',
  2: 'Places your setups on its own, under every gate below',
} as const;

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
};

export const BOT_READOUT_TITLE = 'Read-out to unlock Strategy';
export const BOT_READOUT_STATE_LABELS: Record<string, string> = {
  collecting: 'Collecting',
  passed: 'Passed',
  not_passed: 'Not passed yet',
  failed: 'Failed',
  unavailable: 'Scoreboard not open',
};
export const BOT_READOUT_RULE =
  'Needs 50 go setups triggered, average net R above +0.2 and above blind / wait. Judged on the first 100.';
export const BOT_ERROR_READOUT = 'Strategy waits on the first-pullback read-out';

export const BOT_IN_CONTROL_LABEL = 'Bot is in control';

export const BOT_DESK_ARM_HEADER = 'X-Nova-Desk-Arm';
export const BOT_DESK_ARM_STORAGE = 'nova_bot_desk_arm';
export const BOT_ALLOWLIST_ADD = 'Add to bot allowlist';
export const BOT_ALLOWLIST_REMOVE = 'Remove from bot allowlist';
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
export const BOT_BREAKER_SOFT_LABEL = 'Bot trip $ (locked)';
export const BOT_BREAKER_HARD_LABEL = 'All-stop $ (locked)';
export const BOT_BREAKER_HINT =
  'Locked product thresholds. Session PATCH has no breaker fields. -$50 flattens and drops the bot to L0. -$200 flattens and locks bot plus manual buys until next ET midnight.';

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
