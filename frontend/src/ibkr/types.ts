// Shared TypeScript types for the IBKR trading module.
// Mirrors the JSON shapes returned by backend/routes/trading.py.

export type IbkrMode = 'paper' | 'live' | 'disconnected';

export interface IbkrStatus {
  enabled: boolean;
  connected: boolean;
  mode: IbkrMode;
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
}

export interface DepthBook {
  bids: DepthLevel[];
  asks: DepthLevel[];
  l1_fallback: boolean;
}
