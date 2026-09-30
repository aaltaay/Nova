/**
 * The Cryptos page's wire (ADR 040; AGENTS.md section 3, "The Cryptos page"). Percentages are percent points
 * (2.84 = +2.84%); every number the backend does not know is null -- unknown, never 0.
 */

export type NewsKind = 'catalyst' | 'negative' | 'noise' | 'news';
export type StockSession = 'premarket' | 'regular' | 'after_hours' | 'closed';
export type BridgePhase = 'premarket' | 'regular' | 'after_hours' | 'overnight';
export type BridgeRead = 'ahead' | 'behind' | 'in_line';
export type CandleTf = '15m' | '1h' | '4h' | '1d';
export type Lane = [number, number];

export interface CryptoClock {
  now: number;
  stock_session: StockSession;
  stock_next: { kind: 'premarket' | 'open' | 'close' | 'after_hours_end'; at: number } | null;
  crypto_day_start: number;
  crypto_day_start_et: string;
  regions: { asia: boolean; europe: boolean; us: boolean };
  next_funding: number;
  lanes: {
    asia: Lane[];
    europe: Lane[];
    premarket: Lane[];
    regular: Lane[];
    after_hours: Lane[];
    funding: Lane[];
  };
}

export interface FearGreed {
  value: number;
  label: string | null;
  week_ago: number | null;
  at: number | null;
}

export interface CryptoMarket {
  total_cap_usd: number | null;
  total_cap_change_24h_pct: number | null;
  btc_dominance_pct: number | null;
  btc_dominance_change_24h_pt: number | null;
  total_volume_usd: number | null;
  volume_x_30d: number | null;
  fear_greed: FearGreed | null;
  eth_btc: number | null;
  eth_btc_change_24h_pct: number | null;
  btc_qqq_corr_30d: number | null;
}

export interface CoinWhy {
  kind: NewsKind;
  title: string;
  source: string | null;
  published_ts: number | null;
  url: string | null;
}

export interface CryptoCoin {
  symbol: string;
  name: string;
  rank: number | null;
  price: number | null;
  high_24h: number | null;
  low_24h: number | null;
  change_1h_pct: number | null;
  change_24h_pct: number | null;
  change_7d_pct: number | null;
  volume_24h_usd: number | null;
  volume_x_30d: number | null;
  market_cap_usd: number | null;
  from_ath_pct: number | null;
  spark_7d: number[];
  funding_8h_pct: number | null;
  groups: string[];
  why: CoinWhy | null;
  news_checked: boolean;
  ibkr: { listed: boolean; venue: string | null } | null;
  etf: string | null;
  chart: boolean;
}

export interface CryptoLeverage {
  funding: { symbol: string; funding_8h_pct: number }[];
  open_interest_usd: number | null;
  btc_open_interest_usd: number | null;
  liquidations_24h: null;
  liquidations_note: string | null;
}

export interface Stablecoins {
  supply_usd: number | null;
  change_7d_usd: number | null;
  daily: { date: string; net_usd: number }[];
}

export interface CryptoFlows {
  etf: null;
  etf_note: string | null;
  stablecoins: Stablecoins | null;
}

export interface BridgeRow {
  symbol: string;
  what: string;
  driver: 'BTC' | 'ETH';
  beta: number | null;
  close: number | null;
  last: number | null;
  since_close_pct: number | null;
  implied_pct: number | null;
  read: BridgeRead | null;
  gap_pt: number | null;
}

export interface CryptoBridge {
  reference_close_at: number | null;
  phase: BridgePhase;
  btc_since_close_pct: number | null;
  eth_since_close_pct: number | null;
  rows: BridgeRow[];
  error: string | null;
}

export interface NextEvent {
  at: number;
  kind: 'funding' | 'expiry' | 'stocks' | 'crypto_day';
  title: string;
  detail: string | null;
}

export interface NewsRow {
  published_ts: number;
  symbol: string;
  kind: NewsKind;
  title: string;
  source: string | null;
  url: string | null;
}

export type SourceId = 'coingecko' | 'coinbase' | 'fear_greed' | 'hyperliquid' | 'defillama' | 'deribit' | 'alpaca' | 'ibkr';

export interface SourceStatus {
  id: SourceId;
  label: string;
  ok: boolean | null;
  at: number | null;
  error: string | null;
}

export interface CryptoBoard {
  schema_version: number;
  generated_at: number;
  enabled: boolean;
  loading: boolean;
  replay_desk: boolean;
  clock: CryptoClock;
  market: CryptoMarket;
  coins: CryptoCoin[];
  leverage: CryptoLeverage;
  flows: CryptoFlows;
  bridge: CryptoBridge;
  next: NextEvent[];
  news: NewsRow[];
  sources: SourceStatus[];
}

export interface Candle {
  t: number;
  o: number;
  h: number;
  l: number;
  c: number;
  /** Coinbase's volume in coins; null when it gave none. */
  v: number | null;
}

export interface CandleSession {
  kind: 'premarket' | 'regular' | 'after_hours';
  start: number;
  end: number;
}

export interface CryptoCandles {
  schema_version: number;
  symbol: string;
  tf: CandleTf;
  product: string | null;
  source: string;
  loading: boolean;
  error: string | null;
  candles: Candle[];
  last: number | null;
  change_24h_pct: number | null;
  levels: {
    high_24h: number | null;
    low_24h: number | null;
    day_open: number | null;
    day_open_at: number | null;
    stock_close: { at: number; price: number } | null;
  };
  sessions: CandleSession[];
}
