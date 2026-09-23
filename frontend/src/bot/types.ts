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

export type BotSession = {
  level: 0 | 1 | 2 | 3;
  armed: boolean;
  has_desk_arm?: boolean;
  strategy: string | null;
  /** ADR 027: the setup that plays, the playbook, its read-out and every gate. */
  setup?: string;
  setups?: BotSetupInfo[];
  readout?: BotReadout;
  gates?: BotGate[];
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
    expire_ts: number;
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
