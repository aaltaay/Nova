import {
  SHORT_SETUP_BLURBS,
  SHORT_SETUP_IDS,
  SHORT_SETUP_LABELS,
  SHORT_SETUP_RESEARCH,
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
export const BOT_LEVEL_LABELS = {
  0: 'Off',
  1: 'Eyes',
  2: 'Strategy',
} as const;
export const BOT_STATE_ACTIVE = 'Active';
export const BOT_STATE_NOT_ACTIVE = 'Not active';
export const BOT_API_KEY_HINT = 'Need Nova API key to change the bot';
export const BOT_API_KEY_SAVE = 'Save';
export const BOT_ERROR_NEED_API_KEY =
  'Need Nova API key -- Desktop and Vite read the same repo NOVA_API_KEY, or save it here';
export const BOT_ERROR_ARM_REQUIRED = 'The Bot is off -- turn on the Bot switch in the header first';
export const BOT_ERROR_NOT_ACTIVE = 'The Bot is off -- turn on the Bot switch in the header first';

/* ---------- The playbook (ADR 027): the operator's setups ---------- */
/** Mirrors backend/constants_bot.py BOT_SETUPS. */
export const BOT_SETUP_FIRST_PULLBACK = 'first_pullback';
/** The pullback dip (#847): watch only -- drawn and scored, never traded. */
export const BOT_SETUP_PULLBACK_DIP = 'pullback_dip';
/** The ABCD (operator ask 2026-10-15): watch only -- drawn and scored, never traded. */
export const BOT_SETUP_ABCD = 'abcd';
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
export type BotSetupId = (typeof BOT_SETUP_IDS)[number];

/** Mirrors backend constants_bot.BOT_WATCH_ONLY_SETUPS (#847): the eyes watch, score and draw them; Nova never
 * trades them -- no proposal, no bot, no Auto-entry, no Approve, and On is locked. */
export const BOT_WATCH_ONLY_SETUP_IDS: readonly string[] = [BOT_SETUP_PULLBACK_DIP, BOT_SETUP_ABCD];
export const isWatchOnlySetup = (id: string | null | undefined): boolean =>
  id != null && BOT_WATCH_ONLY_SETUP_IDS.includes(id);
/** A watch-only strategy's Eyes: it draws and scores, and never alerts. */
export const BOT_WATCH_ONLY_LEVEL_TIP =
  'Watch only: at Eyes Nova draws it on your charts, lists it under Setups and scores every trigger -- it never alerts you, and Nova never trades it. On is locked.';
export const BOT_WATCH_ONLY_CHIP = 'Eyes · watch only';
export const BOT_WATCH_ONLY_TAG = 'WATCH ONLY';
export const BOT_WATCH_ONLY_STATUS = 'Watch only';
/** On's lock when an older backend does not say it (the backend's words win). */
export const BOT_WATCH_ONLY_ON_LOCK =
  'On is locked: this strategy is watch only -- Nova draws and scores it, and never trades it (#847).';

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

/** One line on what each setup trades. */
export const BOT_SETUP_BLURBS: Record<string, string> = {
  first_pullback: 'The first 1-3 candle dip after a 5%+ leg to a new high, bought over the pullback high.',
  bull_flag: 'A pole of 3+ green candles on rising volume, then 2-3 quiet red candles that hold the 9 EMA — bought over the flag.',
  gap_and_go: 'Buy the break of the pre-market high on a gapper at the open.',
  flat_top_breakout: 'The high of day tapped 3+ times by tight candles under it, then the first green candle that holds the break.',
  flat_top_5m: 'The same flat top on the 5-minute chart, bought the way the material trades it: the first 1-minute candle that holds the break.',
  red_to_green: 'Trades below the 09:30 open, then back through it — buy the reclaim, one try a day.',
  pullback_dip: 'Watch only: the first pullback\'s run and pullback, bought at the candle that bottoms it — a bottoming wick or the first green close — with the pullback\'s high as target 1.',
  abcd: 'Watch only: a squeeze to the high, a pullback (A), a push that fails under the high (B), a higher low (C) — bought on the break of B, target 1 the high of day.',
  micro_pullback: 'A 1-2 candle dip inside a fast move, read on seconds.',
  ...SHORT_SETUP_BLURBS,
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
    text: 'Bars alone (A2): break-even, and dies on a few cents of slippage. Live with the tape gate: the read-out measures it.',
    detail: 'break-even, dies on a few cents of slippage (A2): the tape gate is what is being tested',
  },
  flat_top_breakout: {
    verdict: 'failed', text: 'Bars alone: failed, -0.83R on 63 trades (P2).', detail: '−0.83R on 63 trades (P2)',
  },
  flat_top_5m: {
    verdict: 'failed',
    text: 'Bars alone (2026-09-29): the 5-minute versions lost less than their 1-minute twins, and still lost. Live with the 1-minute hold and the tape gate: the read-out measures it.',
    detail: 'the 5-minute versions still lost on bars (2026-09-29): the 1-minute hold and the tape gate are what is being tested',
  },
  red_to_green: {
    verdict: 'failed', text: 'Bars alone: failed, -0.22R on 398 trades (P3).', detail: '−0.22R on 398 trades (P3)',
  },
  pullback_dip: {
    verdict: 'not_tested',
    text: 'Never tested: watch only. Its rows and side-by-side target scores are its first evidence (#847).',
    detail: 'watch only: its rows and target scores are its first evidence (#847)',
  },
  abcd: {
    verdict: 'not_tested',
    text: 'Never tested: watch only. Its rows and side-by-side target scores are its first evidence.',
    detail: 'watch only: its rows and target scores are its first evidence',
  },
  micro_pullback: {
    verdict: 'not_tested', text: 'Not tested -- planned on one-second bars (S5).', detail: 'planned on one-second bars (S5)',
  },
  ...SHORT_SETUP_RESEARCH,
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

export const BOT_NO_SCANNER_TITLE = 'No scanner yet -- it cannot watch, propose or trade until it has one';

/** The setups this build has a scanner for -- mirrors backend constants_bot.BOT_SCANNER_SETUPS (ADR 031). */
export const BOT_SCANNER_SETUP_IDS: readonly string[] = [
  'first_pullback', 'bull_flag', 'flat_top_breakout', 'flat_top_5m', 'red_to_green', 'gap_and_go', 'pullback_dip',
  'abcd', ...SHORT_SETUP_IDS,
];
/* A backend older than ADR 031 runs the first pullback only. The page says the backend needs a
   reload -- never "No scanner yet", which would say the feature is missing when it is not loaded. */
export const BOT_STALE_BACKEND_BANNER =
  'Your backend is still running code from before the setup scanners, so only the first pullback is running. '
  + 'Reload it to start the bull flag, flat-top and red to green scanners. '
  + 'A reload takes about half a minute, and a recording picks up where it left off.';
export const BOT_STALE_BACKEND_STATUS = 'Not running yet: the backend needs a reload to start this scanner';
export const BOT_STALE_BACKEND_WHY =
  'The backend is running code from before this scanner -- reload it (gear, Reload backend) to start it';
export const BOT_STALE_BACKEND_TEMPLATE = 'needs a backend reload';

/** A strategy's own switch on its card (ADR 044): Off, Eyes, On (the setup levels 0 / 1 / 2). */
export const BOT_STRATEGY_LEVEL_LABELS = {
  0: 'Off',
  1: 'Eyes',
  2: 'On',
} as const;
/** What each level means on a strategy card (ADR 044). */
export const BOT_SETUP_LEVEL_TIPS = {
  0: 'Off: silent. Its scanner still watches and scores every armed setup, so its read-out keeps collecting, but it never alerts you and draws nothing on your charts.',
  1: 'Eyes: it draws its setups on your charts and alerts you when one comes near its trigger and the tape reads GO: a ping and a card in the inbox. You press Place. The default.',
  2: 'On: everything Eyes does, and while the Bot is on the bot may trade its GO triggers -- a long strategy buys, a short strategy shorts -- on the stocks whose Entry is Bot, inside its bot window, its grades and its setups a day. Live trading by a bot is not built.',
} as const;
export const BOT_SETUP_LEVEL_CHIPS = {
  0: 'Off · silent',
  1: 'Eyes · alerts you',
  2: 'On · Nova may act on it',
} as const;
/** On while the Bot is off: it alerts like Eyes until the Bot is on. */
export const BOT_SETUP_LEVEL_CHIP_WAITING = 'On · alerts you while the Bot is off';
export const BOT_SETUP_LEVEL_WAITING_TIP =
  'This strategy is On, but the Bot is off on this venue, so it alerts you like Eyes. Turn the Bot on and Nova may act on its GO triggers.';
/** A legacy master below the strategy's own level (an older backend): what it may do now is the master's. */
export const botSetupCapped = (own: string, effective: string): string => `${own} · held at ${effective} by the bot`;
export const BOT_SETUP_CAPPED_TIP =
  'The bot\'s level on this venue is below this strategy\'s own switch, so it acts at that level. Turn the Bot on to lift it.';

/* ---------- Gates (backend bot/gates.py, ADR 042) ---------- */
/** Gate ids, in the order the page lists them. */
export const BOT_GATE_LABELS: Record<string, string> = {
  venue: 'Venue',
  level: 'Bot switch',
  setups: 'Strategies at On',
  padlock: 'Padlock',
  strategy_key: 'Strategy Bots key',
  allowlist: 'Nova-buy stocks',
  depth_lines: 'Depth line',
  loss_limit: 'Loss limit',
  kill_switch: 'Freeze all orders',
  window: 'Bot window',
  extended_hours: 'Hours',
  commissions: 'Commissions',
};
/** What each gate checks, on its chip's hover. */
export const BOT_GATE_TIPS: Record<string, string> = {
  venue: 'Nova\'s bot trades Paper, and Sim at the live edge (the playhead on the wall clock). Live trading by a bot is not built, and a Sim replay is the past, so the bot never trades there. The Bot switch needs this.',
  level: 'The Bot switch, in the header beside the padlock: on, Nova may act on the strategies at On; off, no bot places an order and the strategies alert you like Eyes. Turning a strategy On, a TraderTV host Bot key on or a family key on turns it on too. Each venue keeps its own.',
  strategy_key: 'The Strategy Bots key, at the top of this page: off, the strategies\' bot and Auto-entry place no order, not even a sell. Each venue keeps its own. Checked on every order.',
  setups: 'At least one strategy set to On on its card. Nova acts only on those strategies\' GO triggers. The Bot switch needs this.',
  padlock: 'The desk padlock (spend arming). It is locked at every start and when anyone locks it. No bot turns on while it is locked: turning one on asks you to unlock it first. Locked after a bot is on, no one places an order, a bot included; the Bot switch reads LOCKED, and the bots trade again once you unlock it.',
  allowlist: 'The stocks whose Buy is Bot on this venue (Tickers today, or Who trades on a Trader tab). The bot buys nothing else; the scanners and Eyes still watch every HOD Momo name.',
  depth_lines: 'Nova must hold a stock\'s Level 2 line to read its tape at the trigger (IBKR allows 3 at once). This is open while one bot stock has a line; a trigger on a stock without one is skipped, and the activity says so. Checked on every order.',
  loss_limit: 'No new buys after the daily loss limit (Settings > Loss limits): with No new buys checked, once this venue\'s day loss reaches the limit, buys -- yours and the bots\' -- are refused until 04:00 ET on the next trading day; once the bots\' own trades reach the Bots\' trades line, only the bots\' entries are. Selling, Flatten and KILL still work. Checked on every order.',
  kill_switch: 'Freeze all orders cancels every working order on every venue and refuses every new order on every venue -- yours and Nova\'s, a sell included -- until you unfreeze them. Flatten and cancels still work. Checked on every order.',
  window: 'Each setup\'s bot window, from its template and inside its arming window: the bot buys only a trigger inside it. Open while any setup at Strategy is inside its window now. Checked on every order.',
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
  + 'Results are information for you to judge; they never unlock trading.';
/** How it scores, against how the bot trades (ADR 042 G). */
export const BOT_READOUT_EXITS =
  'It scores the strategy\'s exit (its share at target 1, the rest at target 2, the stop where it is); '
  + 'the bot sells everything at target 1, with a 15-minute time stop.';
/** The read-out's hover: what it measures, what it does not unlock, and how it scores. */
export const BOT_READOUT_TIP = (setup: string): string =>
  `${BOT_READOUT_WHAT}\n`
  + `It counts every ${setup} this template armed that triggered, split by what the tape said at the trigger. `
  + 'GO: the tape said go. Blind / wait: Nova held no Level 2 line, or the tape said wait — the control group.\n'
  + 'It passes at 50 go setups whose average net R (after a cent of slippage each way) is above +0.2 and above the control\'s, '
  + 'judged on the first 100 go setups; 100 without a pass is failed.\n'
  + 'It scores the strategy\'s exit — its share at target 1, the rest at target 2, the stop staying where it is — '
  + 'while Nova\'s bot sells everything at target 1, with a 15-minute time stop. Its triggers outside the bot\'s window count here, '
  + 'though the bot would never have bought them.';
export const botReadoutInside = (triggered: number, go: number, start: string, end: string): string =>
  `${triggered} triggered inside the bot window ${start}–${end} (${go} at GO)`;

export const BOT_DESK_ARM_HEADER = 'X-Nova-Desk-Arm';
export const BOT_DESK_ARM_STORAGE = 'nova_bot_desk_arm';

/* ---------- The bot's stocks (ADR 042 F): set per stock, one owner ----------
   Adding a stock to the bot sets it to Bot (bot buys and sells) through the
   stock-mode rules; a refusal is shown in the backend's own words. */
export const botTradeAddLabel = (symbol: string): string => `Let the bot trade ${symbol} (bot buys and sells)`;
export const botTradeRemoveLabel = (symbol: string): string => `Stop the bot trading ${symbol}`;
export const botTradeRefusedTitle = (symbol: string, add: boolean): string =>
  (add ? `The bot cannot trade ${symbol}` : `${symbol} stays with the bot`);

/** The right-click symbol menu (bot/BotSymbolMenu): the symbol once in the head, then one row per action. */
export const SYMBOL_MENU_CAPTION = 'Symbol actions';
export const SYMBOL_MENU_PIN_HINT = 'Keep this tab when you open another symbol';
export const SYMBOL_MENU_UNPIN_HINT = 'The next symbol you open may replace it';
export const SYMBOL_MENU_RECORD = 'Start recording';
export const SYMBOL_MENU_RECORD_HINT = 'Save its tape and Level 2 for Sim replay';
export const SYMBOL_MENU_STOP_RECORD = 'Hold to stop recording';
export const SYMBOL_MENU_REC_STATE = 'REC';
export const SYMBOL_MENU_ALLOW_HINT = 'Sets it to Bot under Who trades: Nova\'s bot may buy it and sell it on this venue';
export const SYMBOL_MENU_UNALLOW_HINT = 'Back to Signal only: Nova stops buying it (an open trade keeps its exits)';
export const SYMBOL_MENU_ALLOW_STATE = 'Bot';
export const SYMBOL_MENU_BOT_BUSY_WHY = 'Asking Nova -- wait for the answer';
/** Mirrors backend/constants_bot.py -- the bot's stocks, not the sleeve's order kinds. */
export const BOT_SYMBOL_ALLOWLIST_CAP = 50;

/* ---------- QA batch: orders / account / safety (2026-09-22) ---------- */
/** Endpoint names in "unreadable response" errors (botPayload.botUnreadableMessage). */
export const BOT_LABEL_SESSION = 'Bot session';
export const BOT_LABEL_PROPOSALS = 'Bot proposals';
export const BOT_LABEL_AUDIT = 'Bot audit';

/* ---------- Kill switch (D-037, ADR 025, ADR 042 D) ---------- */
/** The one kill latch, in the words of what it does: on the desk it is "Freeze all orders" (ADR 044). */
export const KILL_SWITCH_TITLE = 'Freeze all orders';
export const KILL_SWITCH_HINT =
  'Freezes every order: cancels every working order on every venue -- except a stop that protects a position you hold, which stays resting -- and refuses every new order on every venue -- from you or from Nova, a sell included -- until you unfreeze. It sells nothing: Flatten and cancels still work. It stays on across a restart. The red KILL at the top of the desk is the one that sells: it turns the bot off, locks the padlock, cancels everything and flattens this venue.';
export const KILL_SWITCH_TRIP_LABEL = 'Freeze all orders';
export const KILL_SWITCH_RESET_LABEL = 'Unfreeze orders';
export const KILL_SWITCH_TRIP_CONFIRM =
  'Freeze all orders? It cancels every working order on every venue but the stops that protect a position, and refuses every new order on every venue, a sell included, until you unfreeze. It sells nothing; Flatten and cancels still work.';
export const KILL_SWITCH_RESET_CONFIRM = 'Unfreeze orders? New orders will be allowed again.';
export const KILL_SWITCH_POLL_MS = 5000;

/**
 * No bot turns on while the desk padlock is locked (operator decision 2026-10-20; `bot/padlockPrompt.ts`, backend
 * `bot/padlock_gate.py`): the one question every bot's On asks over a locked padlock.
 */
export const BOT_PADLOCK_REFUSAL_CODE = 'BOT_PADLOCK_LOCKED';
export const BOT_PADLOCK_PROMPT_TITLE = 'Unlock the padlock?';
export const BOT_PADLOCK_PROMPT_MESSAGE =
  'The desk padlock is locked. While it is locked no bot places an order -- not a buy, not a sell -- so a bot turned on would only look on. Unlock the padlock and turn the bot on?';
export const BOT_PADLOCK_PROMPT_CONFIRM = 'Unlock and turn on';
export const BOT_PADLOCK_PROMPT_CANCEL = 'Keep it off';
export const BOT_PADLOCK_KEPT_OFF = 'Kept off: the padlock stays locked, so no bot turned on.';
export const BOT_PADLOCK_UNLOCK_FAILED = 'The padlock did not unlock, so no bot turned on';
/** The header Bot switch while it is on but the padlock is locked: never ON over a padlock that blocks every order. */
export const BOT_SWITCH_LOCKED_NAME = 'LOCKED';
export const BOT_SWITCH_LOCKED_REASON =
  'The padlock is locked: no bot places an order, not even a sell, until you unlock it (the padlock beside this switch)';
