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
  /** Sim practice fills only: inferred from a replay, never a real execution (ADR 019). */
  fill_estimated?: boolean | null;
  fill_basis?: string | null;
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

export type TrailEventKind =
  | 'place'
  | 'fill'
  | 'flatten'
  | 'cancel'
  | 'replace'
  | 'commission'
  | 'close';

export interface TrailEvent {
  kind: TrailEventKind | string;
  ts: number | null;
  execution_id?: string | null;
  symbol?: string | null;
  operation?: string | null;
  source?: string | null;
  side?: string | null;
  qty?: number | null;
  price?: number | null;
  commission?: number | null;
  pnl?: number | null;
  status?: string | null;
  broker_status?: string | null;
  order_id?: number | null;
}

export interface TrailItem {
  id: string;
  kind: 'closed' | 'open' | string;
  trade_id?: number | null;
  symbol: string | null;
  side?: string | null;
  qty?: number | null;
  entry_price?: number | null;
  exit_price?: number | null;
  pnl?: number | null;
  commission?: number | null;
  pnl_basis?: 'net' | 'gross' | null;
  opened_ts?: number | null;
  closed_ts?: number | null;
  close_key?: string | null;
  notes?: string | null;
  events: TrailEvent[];
  fill_ids?: string[];
}

export interface TrailPayload {
  count: number;
  includes_mock_data: boolean;
  items: TrailItem[];
}
