// Shared TypeScript types for the IBKR trading module.
// Mirrors the JSON shapes returned by backend/routes/trading.py.

export type IbkrMode = 'paper' | 'live' | 'disconnected';

export interface IbkrStatus {
  enabled: boolean;
  /**
   * Product usable session (READY / get_ib() non-null).
   * Not the same as the TCP socket -- see transport_connected.
   */
  connected: boolean;
  /** Raw Gateway socket up (may be true while session is not usable, e.g. Error 1100). */
  transport_connected?: boolean;
  /** Usable-session SoT reason from /api/ibkr/status (ok, connectivity_lost, ...). */
  session_reason?: string;
  mode: IbkrMode;
  gateway_mode?: 'paper' | 'live';
  /** Session account classification from IB account ids (DU…=paper, U…=live). */
  broker_account_kind?: 'paper' | 'live' | 'unknown';
  /** Last requested IB market-data type (1=live); null before first READY. */
  market_data_type?: number | null;
  /** True after IB Error 10167 (delayed / non-entitled feed). */
  market_data_delayed?: boolean;
  orders_enabled?: boolean;
  live_trading_confirmed?: boolean;
  /** Phase K / ADR 009 -- third key for opening shorts. */
  short_enabled?: boolean;
  /** locked | locked_live_unconfirmed | paper_armed | live_armed */
  spend_status?: string;
  preferred_port?: number;
  alternate_port?: number;
  preferred_port_reachable?: boolean;
  alternate_port_reachable?: boolean;
  /** e.g. paper_port_refused_live_listening -- see disconnectCopy.ts */
  disconnect_hint?: string | null;
  intentional_gateway_mode?: 'paper' | 'live' | null;
  /** A Second Factor prompt is currently open on the Gateway desktop. */
  second_factor_pending?: boolean;
  /** Seconds since that prompt opened (null when none is pending). */
  second_factor_age_sec?: number | null;
  /** True once the prompt has sat open longer than IBC's own timeout --
   * IBC will silently discard it even if approved a moment later. */
  second_factor_stale?: boolean;
  gateway_self_heal?: {
    from_mode?: string;
    to_mode?: string;
    reason?: string;
    preferred_port?: number;
    healed_port?: number;
    persisted?: boolean;
  } | null;
}

export interface IbkrAccountSummary {
  connected: boolean;
  mode: IbkrMode;
  NetLiquidation?: number | null;
  TotalCashValue?: number | null;
  BuyingPower?: number | null;
  UnrealizedPnL?: number | null;
  RealizedPnL?: number | null;
  GrossPositionValue?: number | null;
  error?: string;
}

export interface IbkrPosition {
  symbol: string;
  qty: number;
  market_price: number | null;
  market_value: number | null;
  avg_cost: number | null;
  unrealized_pnl: number | null;
  realized_pnl: number | null;
}

export interface IbkrOrder {
  order_id: number;
  /** IB permId -- durable across reconnect. Session orderId may be 0. */
  perm_id?: number | null;
  /** nova = placed through ADR 007; ib_recovered = IB-only / TWS. */
  source?: 'nova' | 'ib_recovered';
  symbol: string;
  side: 'BUY' | 'SELL';
  qty: number;
  /** Shares already filled (IBKR orderStatus.filled). */
  filled_qty?: number | null;
  /** Shares still working (IBKR orderStatus.remaining). */
  remaining_qty?: number | null;
  order_type: 'MKT' | 'LMT' | 'STP';
  limit_price: number | null;
  stop_price?: number | null;
  /** Average fill price when any fills exist. */
  avg_fill_price?: number | null;
  outside_rth?: boolean;
  status: string;
  /** ISO-8601 UTC when the order was first seen / submitted (IBKR trade log). */
  submitted_at?: string | null;
  /** ISO-8601 UTC of last fill or last status change (prefer fill time). */
  updated_at?: string | null;
  /** ISO-8601 UTC of the last real broker fill; null when the order never filled. */
  filled_at?: string | null;
  /** ISO-8601 UTC when IB Warning 399 holds the order until RTH open. */
  held_until?: string | null;
}

export interface DepthLevel {
  price: number;
  size: number;
  side: 'bid' | 'ask';
  /** Market maker / exchange id from IBKR Smart Depth (e.g. ISLAND, ARCA). */
  mm?: string;
}

export interface DepthBook {
  bids: DepthLevel[];
  asks: DepthLevel[];
  l1_fallback: boolean;
  /** Set by the depth WS / hook — used to reject cross-symbol stale books. */
  symbol?: string;
}
