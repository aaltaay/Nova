import type { BotActionKind } from '../constantGroups/bot';

export type BotSession = {
  level: 0 | 1 | 2 | 3;
  armed: boolean;
  strategy: string | null;
  brain_session_id: string | null;
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
