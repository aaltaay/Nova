export interface ActivityTimings {
  validation_ms: number | null;
  persisted_ms: number | null;
  broker_sent_ms: number | null;
  broker_ack_ms: number | null;
  filled_ms: number | null;
}

export interface ActivityRow {
  id: string;
  created_ts: number;
  updated_ts?: number;
  operation: string;
  source: string;
  symbol: string | null;
  side: string | null;
  requested_qty: number | null;
  sent_qty: number | null;
  forced_one_share: boolean;
  orders_enabled?: boolean | null;
  live_trading_confirmed?: boolean | null;
  short_enabled?: boolean | null;
  short_entry?: boolean;
  gateway_mode?: string | null;
  order_id?: number | null;
  perm_id?: number | null;
  filled_qty?: number | null;
  avg_fill_price?: number | null;
  status: string;
  broker_status?: string | null;
  reason_code?: string | null;
  error?: string | null;
  mode?: string | null;
  timings: ActivityTimings;
}

export interface ActivityFillEvidence {
  provenance?: string;
  fill_state?: string;
  shares?: number | null;
  price?: number | null;
  average_fill_price?: number | null;
  slippage_per_share?: number | null;
  leg_role?: string | null;
}

export interface ActivityDetail extends ActivityRow {
  fill_evidence?: ActivityFillEvidence[];
}
