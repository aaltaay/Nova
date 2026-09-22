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

/** Where a live trade update came from: a print, a Level 1 snapshot (a last price, not a print), or a replayed print. */
export type TradeUpdateSource = 'stream' | 'snapshot' | 'sim';

export interface TradeData {
  price: number | null;
  size: number | null;
  exchange: string | null;
  timestamp: string | null;
  /** Absent on REST snapshots; set from the socket's trade updates. */
  source?: TradeUpdateSource;
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
  /** Phase K shortability state (ADR 009). */
  state?: 'shortable_est' | 'thin' | 'htb_likely' | 'unknown' | string | null;
  fetched_at?: number | null;
  age_sec?: number | null;
  stale?: boolean | null;
  ttl_sec?: number | null;
  orderable?: boolean | null;
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
  /**
   * `snapshot` is IBKR's Level 1 last at request time -- after the close that
   * can be the regular session's last while the tape trades elsewhere. It may
   * update the quote box; it must never paint a candle (QA 2026-09-22).
   */
  source?: TradeUpdateSource;
  /** IBKR reprice ticks include this so gap % stays aligned with the scanner row. */
  prev_close?: number | null;
}

/** Nasdaq Trade Halt RSS overlay -- missing fields stay null, never invented. */
export interface HaltExchangeOverlay {
  status: 'ok' | 'pending' | 'down' | string;
  matched: boolean;
  reason_code?: string | null;
  pause_threshold?: string | null;
  official_halt_start?: number | null;
  quote_resume?: number | null;
  trade_resume?: number | null;
}

/** IBKR ticker.halted snapshot for the L2 HaltEtaChip (incoming tick type 49). */
export interface HaltSnapshot {
  halted: boolean;
  kind: 'luld' | 'regulatory' | 'unknown' | string;
  halt_code?: number | null;
  halt_start?: number | null;
  halt_start_source?: string | null;
  start_late?: boolean;
  reason?: string | null;
  rule?: string | null;
  source?: string | null;
  exchange?: HaltExchangeOverlay | null;
}

export interface TickerDetail {
  symbol: string;
  asset: AssetInfo;
  /** Dual-broker listing flags (Alpaca Assets + IBKR short/qualify). */
  listing?: ListingCompare | null;
  /** Live IBKR halt (ticker.halted). Null/absent = not halted; quiet tape is not enough. */
  halt?: HaltSnapshot | null;
  snapshot: SnapshotData;
  avg_volume: number | null;
  rel_volume: number | null;
  /** momentum Rel Vol (5 min) — last-5m vol ÷ typical 5m bar; null until buffer warm. */
  rvol_5min?: number | null;
  /** Shares traded in the last ~5 minutes from cum-vol deltas. */
  volume_in_5min?: number | null;
  news: NewsArticle[];
  fundamentals: FundamentalsData | null;
  mode: string | null;
  news_impact?: NewsImpactVerdict | null;
}
