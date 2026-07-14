// Shared TypeScript types for the IBKR trading module.
// Mirrors the JSON shapes returned by backend/routes/trading.py.

export type IbkrMode = 'paper' | 'live' | 'disconnected';

export interface IbkrStatus {
  enabled: boolean;
  connected: boolean;
  mode: IbkrMode;
  gateway_mode?: 'paper' | 'live';
  orders_enabled?: boolean;
  live_trading_confirmed?: boolean;
  /** locked | locked_live_unconfirmed | paper_armed | live_armed */
  spend_status?: string;
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
  symbol: string;
  side: 'BUY' | 'SELL';
  qty: number;
  order_type: 'MKT' | 'LMT';
  limit_price: number | null;
  status: string;
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
}
