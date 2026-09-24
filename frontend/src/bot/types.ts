import type { BotActionKind } from '../constantGroups/bot';

/** One setup of the operator's playbook (ADR 027); only one with a scanner can play. */
export type BotSetupInfo = { id: string; scanner: boolean };

export type BotReadoutBlock = {
  triggered: number;
  scored: number;
  win_pct: number | null;
  avg_net_r: number | null;
};

/** The first-pullback read-out that unlocks Strategy (backend setup_scanner/readout.py). */
export type BotReadout = {
  state: 'collecting' | 'passed' | 'not_passed' | 'failed' | 'unavailable' | string;
  passed: boolean;
  reason: string;
  go: BotReadoutBlock;
  control: BotReadoutBlock;
  rules: { kind?: string; min_go: number; fail_go?: number; min_net_r?: number };
};

/** One gate between the bot and a fire (backend bot/gates.py). */
export type BotGate = {
  id: string;
  ok: boolean;
  stage: 'activate' | 'fire' | string;
  detail: Record<string, unknown>;
};

/** Nova's own first-pullback bot (backend bot/first_pullback, ADR 030): does it play, and why not. */
export type BotRunner = { brain_id: string; playing: boolean; reason: string | null };

/** The first-pullback bot's current or last trade (ADR 030). Prices are the venue's; r is gross, per the setup's risk. */
export type BotTrade = {
  setup_id: string;
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
  exit_reason: 'target' | 'stop' | 'time' | 'outside' | string | null;
  exit_why?: string | null;
  slippage: number | null;
  r: number | null;
  note?: string | null;
};

export type BotSession = {
  level: 0 | 1 | 2 | 3;
  armed: boolean;
  has_desk_arm?: boolean;
  strategy: string | null;
  /** ADR 027: the setup that plays, the playbook, its read-out and every gate. */
  setup?: string;
  setups?: BotSetupInfo[];
  readout?: BotReadout;
  /** ADR 030: false on Paper and Sim, where Strategy does not wait on the read-out. */
  readout_required?: boolean;
  gates?: BotGate[];
  runner?: BotRunner;
  trade?: BotTrade | null;
  symbol_allowlist?: string[];
  brain_session_id: string | null;
  brain_heartbeat_ts?: number | null;
  brain_alive?: boolean;
  live_fire_ready?: boolean;
  trading_allowed?: boolean;
  trading_allowed_reason?: string | null;
  caps: {
    max_shares: number;
    bp_budget_usd: number;
    working_ttl_sec: number;
    extended_hours: boolean;
    allowlist: BotActionKind[];
  };
  advise: {
    enabled: boolean;
    usd_cap: number;
    call_cap: number;
    usd_spent: number;
    calls_used: number;
  };
  soft_breaker_fired: boolean;
  hard_lock_until_date: string | null;
  day_lock_active: boolean;
  focus: string[];
  trader_live: string[];
  working: Array<{
    order_id: number;
    symbol: string;
    side: string;
    qty: number;
    price: number;
    kind: string;
    /** Null for an order its owner cancels itself (the first-pullback bot's entry, ADR 030). */
    expire_ts: number | null;
  }>;
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
  strategy: string | null;
  brain_session_id: string | null;
  action: string;
  inputs: Record<string, unknown>;
  reason: string | null;
  order_id: number | null;
  advise_spend: number | null;
  outcome: string;
};
