/** Shared ticker-detail types (mirrors /ws/ticker/{symbol} payloads). */
import type { NewsImpactVerdict } from './newsImpact';

export interface BarData {
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
  trade_count: number | null;
  vwap: number | null;
  timestamp: string | null;
}

export interface TradeData {
  price: number | null;
  size: number | null;
  exchange: string | null;
  timestamp: string | null;
}

export interface QuoteData {
  bid_price: number | null;
  bid_size: number | null;
  ask_price: number | null;
  ask_size: number | null;
  timestamp: string | null;
}

export interface SnapshotData {
  latest_trade: TradeData | null;
  latest_quote: QuoteData | null;
  minute_bar: BarData | null;
  daily_bar: BarData | null;
  prev_daily_bar: BarData | null;
  prev_close: number | null;
  session_close: number | null;
  session_prev_close: number | null;
}

export interface AssetInfo {
  name?: string;
  exchange?: string;
  asset_class?: string;
  status?: string;
  tradable?: boolean;
  marginable?: boolean;
  shortable?: boolean;
  easy_to_borrow?: boolean;
  fractionable?: boolean;
  maintenance_margin_requirement?: number | null;
  margin_requirement_long?: string | null;
  margin_requirement_short?: string | null;
  attributes?: string[];
}

/** Side-by-side broker listing — never merge Alpaca + IBKR into one Yes/No. */
export interface AlpacaListingFlags {
  source: 'alpaca_assets' | string;
  status?: string | null;
  tradable?: boolean | null;
  shortable?: boolean | null;
  easy_to_borrow?: boolean | null;
  short_type?: string | null;
  short_type_detail?: string | null;
  marginable?: boolean | null;
  fractionable?: boolean | null;
  maintenance_margin_requirement?: number | null;
  margin_requirement_long?: string | null;
  margin_requirement_short?: string | null;
  asset_class?: string | null;
  exchange?: string | null;
  attributes?: string[];
  error?: string | null;
}

export interface IbkrListingFlags {
  source: 'ibkr' | string;
  connected?: boolean;
  qualified?: boolean;
  con_id?: number | null;
  long_name?: string | null;
  stock_type?: string | null;
  exchange?: string | null;
  shortable_shares?: number | null;
  short_type?: string | null;
  short_type_detail?: string | null;
  tradable_hint?: string | null;
  error?: string | null;
}

export interface ListingCompare {
  symbol: string;
  alpaca: AlpacaListingFlags;
  ibkr: IbkrListingFlags | null;
}

export interface NewsArticle {
  headline: string;
  summary: string;
  author: string;
  source: string;
  url: string;
  created_at: string;
  symbols: string[];
  images: { url: string; size: string }[];
}

export interface FundamentalsData {
  market_cap: number | null;
  shares_outstanding: number | null;
  float_shares: number | null;
  short_interest: number | null;
  short_ratio: number | null;
  short_percent_of_float: number | null;
  pe_ratio: number | null;
  forward_pe: number | null;
  eps: number | null;
  sector: string | null;
  industry: string | null;
  fifty_two_week_high: number | null;
  fifty_two_week_low: number | null;
  dividend_yield: number | null;
  beta: number | null;
  earnings_date: string | null;
  recent_split: string | null;
}

export interface TickerTradeUpdate {
  type: 'trade_update';
  /** Present on IBKR broadcasts — clients must ignore mismatches vs selected symbol. */
  symbol?: string;
  price: number;
  size: number | null;
  timestamp: string | null;
  volume: number | null;
  /** IBKR reprice ticks include this so gap % stays aligned with the scanner row. */
  prev_close?: number | null;
}

export interface TickerDetail {
  symbol: string;
  asset: AssetInfo;
  /** Dual-broker listing flags (Alpaca Assets + IBKR short/qualify). */
  listing?: ListingCompare | null;
  snapshot: SnapshotData;
  avg_volume: number | null;
  rel_volume: number | null;
  /** Warrior Rel Vol (5 min) — last-5m vol ÷ typical 5m bar; null until buffer warm. */
  rvol_5min?: number | null;
  /** Shares traded in the last ~5 minutes from cum-vol deltas. */
  volume_in_5min?: number | null;
  news: NewsArticle[];
  fundamentals: FundamentalsData | null;
  mode: string | null;
  news_impact?: NewsImpactVerdict | null;
}
