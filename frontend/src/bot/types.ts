import type { BotActionKind } from '../constantGroups/bot';

/** The master ceiling and each setup's own level (ADR 042): 0 Off, 1 Eyes, 2 Strategy. */
export type BotLevel = 0 | 1 | 2;

/**
 * One setup of the operator's playbook (ADR 027, ADR 042). `level` is the setup's own
 * switch (0 Off, 1 Eyes, 2 Strategy; null without a scanner); `effective` is
 * min(master level, own level) -- what it may do now. Absent on an older API.
 */
export type BotSetupInfo = { id: string; scanner: boolean; level?: number | null; effective?: number | null };

/** One venue's loss breakers (ADR 032): negative dollars, the bot trip above the all-stop. */
export type BotBreakerPair = { soft_usd: number; hard_usd: number };

/** The loss breakers the Bots page draws (ADR 032): the desk venue's, every venue's, and the bounds. */
export type BotBreakers = BotBreakerPair & {
  venue: 'live' | 'paper' | 'sim' | string;
  /** The operator moved this venue's pair (false: the defaults). */
  custom: boolean;
  defaults: BotBreakerPair;
  by_venue: Record<string, BotBreakerPair>;
  /** [loosest, tightest] for each, and the step the backend snaps to. */
  bounds: { soft_usd: [number, number]; hard_usd: [number, number]; step_usd: number };
  /** Why the breakers compare nothing now (a Sim replay's P&L is not today's), or null. */
  note?: string | null;
};

/** One gate between the bot and a trade (backend bot/gates.py). */
export type BotGate = {
  id: string;
  ok: boolean;
  /** `activate`: Activate needs it; `fire`: each order meets it. */
  stage: 'activate' | 'fire' | string;
  detail: Record<string, unknown>;
};

/** Nova's own bot (backend bot/first_pullback, ADR 030): does it play, and why not. */
export type BotRunner = { brain_id: string; playing: boolean; reason: string | null };

/** The bot's current or last trade (ADR 030). Prices are the venue's; r is gross, per the setup's risk. */
export type BotTrade = {
  setup_id: string;
  /** ADR 042: the setup that triggered it (every setup at Strategy plays). */
  setup_type?: string | null;
  symbol: string;
  venue: string;
  venue_day: string;
  template_id?: string | null;
  state: 'entering' | 'open' | 'exiting' | 'closed' | 'missed' | string;
  qty: number;
  trigger?: number | null;
  entry_planned: number;
  stop: number;
  target1: number;
  risk: number;
  entry_fill_price: number | null;
  exit_price: number | null;
  exit_reason: 'target' | 'stop' | 'time' | 'flush' | 'outside' | 'handed' | string | null;
  exit_why?: string | null;
  slippage: number | null;
  r: number | null;
  note?: string | null;
};

/** Why Activate was cleared (ADR 042): the backend clears it and says so. */
export type BotDeactivated = {
  at: number | null;
  reason: 'restart' | 'padlock' | 'venue' | 'level' | 'no_setup' | 'bot_trip' | 'all_stop' | 'operator' | string;
  text: string | null;
};

/** One venue's sleeve (ADR 042): every Nova automatic buy on that venue is sized and capped by it. */
export type BotCaps = {
  venue?: string | null;
  /** Risk per trade: shares = risk / risk per share, capped by max shares and the budget. */
  risk_usd?: number | null;
  max_shares: number;
  bp_budget_usd: number;
  working_ttl_sec: number;
  extended_hours: boolean;
  /** One count for the bot and Auto-entry per venue day. */
  entries_per_day?: number | null;
  /** The localhost bot API's order kinds. */
  api_kinds: BotActionKind[];
  /** LEGACY alias of `api_kinds` (one release). */
  allowlist?: BotActionKind[];
};

export type BotCapsBounds = {
  risk_usd: [number, number];
  max_shares: [number, number];
  bp_budget_usd: [number, number];
  working_ttl_sec: [number, number];
  entries_per_day: [number, number];
};

/** One of today's Nova automatic entries (the bot or Auto-entry) on this venue. */
export type BotEntry = { symbol: string; setup_type: string | null; by: 'bot' | 'auto_entry' | string; ts: number; outcome: string };

/** Nova's automatic entries today on this venue: one count for the bot and Auto-entry (ADR 042). */
export type BotEntriesToday = {
  count: number;
  cap: number;
  venue_day: string | null;
  entries: BotEntry[];
  /** Approve's brackets sent today: the operator's own, counted and never capped. */
  approved: number;
};

/** The all-stop's lock on one venue: buys wait until `until` (the next 04:00 ET). */
export type BotDayLock = {
  active: boolean;
  until: string | number | null;
  tripped_at: string | number | null;
  pnl: number | null;
  venue: string | null;
};

/** The bot trip on this venue today: when it fired, at what P&L, and when it clears. */
export type BotSoftBreaker = {
  fired: boolean;
  at: string | number | null;
  pnl: number | null;
  until: string | number | null;
};

export type BotWorkingOrder = {
  order_id: number;
  symbol: string;
  side: string;
  qty: number;
  price: number;
  kind: string;
  /** Null for an order its owner cancels itself (the bot's entry, ADR 030). */
  expire_ts: number | null;
};

/**
 * `GET /api/bot/session`: the desk venue's dial (file schema 5, ADR 042). The page reads
 * `active` and `ready`; `armed` and `live_fire_ready` are their legacy aliases, which
 * botPayload.parseBotSession folds in so a reader never sees one without the other.
 */
export type BotSession = {
  /** The master ceiling: the most any setup may do on this venue. */
  level: BotLevel | 3;
  /** Activate is on. */
  active: boolean;
  /** LEGACY alias of `active`. */
  armed?: boolean;
  has_desk_arm?: boolean;
  /** Why Activate was cleared last; null while active or never cleared. */
  deactivated?: BotDeactivated | null;
  setups?: BotSetupInfo[];
  /** Every setup with a scanner: 0 Off, 1 Eyes, 2 Strategy. */
  setup_levels?: Record<string, number>;
  /** The bot would trade a go trigger now, and the one reason it would not. */
  ready: boolean;
  ready_reason?: string | null;
  /** LEGACY alias of `ready`. */
  live_fire_ready?: boolean;
  gates?: BotGate[];
  /** ADR 032: the loss breakers, per venue. */
  breakers?: BotBreakers;
  runner?: BotRunner;
  trade?: BotTrade | null;
  /** This venue's Bot stocks (Nova buys and sells). */
  symbol_allowlist?: string[];
  caps: BotCaps;
  caps_bounds?: BotCapsBounds;
  caps_by_venue?: Record<string, BotCaps>;
  entries_today?: BotEntriesToday;
  day_lock?: BotDayLock;
  soft_breaker?: BotSoftBreaker;
  soft_breaker_fired: boolean;
  /** LEGACY (this venue's): read `day_lock`. */
  hard_lock_until_date: string | null;
  day_lock_active: boolean;
  level_venue?: string | null;
  levels_by_venue?: Record<string, number>;
  brain_session_id: string | null;
  brain_heartbeat_ts?: number | null;
  brain_alive?: boolean;
  trading_allowed?: boolean;
  trading_allowed_reason?: string | null;
  /** The bot `advise` budget: absent once the backend retired it (ADR 042 K). */
  advise?: {
    enabled: boolean;
    usd_cap: number;
    call_cap: number;
    usd_spent: number;
    calls_used: number;
  };
  focus?: string[];
  trader_live?: string[];
  working: BotWorkingOrder[];
  updated_ts?: number;
  desk_arm_token?: string;
};

export type BotProposal = {
  id: string;
  symbol: string;
  side: string;
  kind: string;
  shortcut: string;
  preset_qty: number;
  reason: string;
  confidence: number | null;
  status: string;
};

export type BotAuditEntry = {
  timestamp: number;
  level: number;
  strategy?: string | null;
  brain_session_id: string | null;
  action: string;
  inputs: Record<string, unknown>;
  reason: string | null;
  order_id: number | null;
  advise_spend?: number | null;
  outcome: string;
  /** The venue the line belongs to (every bot audit line carries it since 2026-09-30). */
  venue?: string | null;
};
