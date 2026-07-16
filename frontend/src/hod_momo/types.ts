/** TypeScript interfaces for the HOD Momo Scanner feature. */

export type StrategyId = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12;

/** Distinct strategy that fired for a symbol (one-row-per-symbol feed). */
export interface AlertStrategyTag {
  id: number;
  name: string;
}

export interface AlertObject {
  id: string;
  timestamp: string;          // ISO-8601
  ticker: string;
  strategy_id: number;
  strategy_name: string;
  price: number;
  change_pct: number;
  rvol: number | null;
  rvol_5min?: number | null;
  float_shares: number | null;
  gap_pct: number | null;
  volume: number | null;
  momentum_pct: number | null;
  rvol_source: string | null;     // "alpaca" | "yfinance" | "yfinance_pace" | ...
  consolidation_count: number;
  consolidated_ids: string[];
  /** Actual burst span in seconds for Warrior-style "(3 in 5sec)". */
  consolidation_span_sec?: number | null;
  created_ts?: number;
  /**
   * Distinct strategies that fired for this ticker when the feed is collapsed
   * to one row per symbol. Newest-first. Absent on raw stream alerts.
   */
  strategies?: AlertStrategyTag[];
}

export interface StrategyConfig {
  strategy_id: number;
  name: string;
  color: string;
  enabled: boolean;
  audio: boolean;
  notes: string;
  min_price: number;
  max_price: number;
  min_float: number;
  max_float: number;
  min_volume: number;
  min_rvol: number;
  max_rvol: number;
  min_gap_pct: number;
  max_gap_pct: number;
  min_change_pct: number;
  max_change_pct: number;
  surge_pct: number;
  surge_window_min: number;
  surge_method: 'low_to_current' | 'fixed_start';
  proximity_52wk_pct: number;
  former_momo_list: string[];
  requires_hod: boolean;
}

export interface MasterGateConfig {
  hod_required: boolean;
  surge_pct: number;
  surge_window_min: number;
  min_rvol: number;
  premarket_min_rvol: number;
  afterhours_min_rvol: number;
  cooldown_sec: number;
  consolidation_sec: number;
}

export interface HodMomoConfigState {
  master: MasterGateConfig;
  strategies: Record<string, StrategyConfig>;
  loaded: boolean;
}

export type HodMomoConfigAction =
  | { type: 'LOADED'; payload: { master: MasterGateConfig; strategies: Record<string, StrategyConfig> } }
  | { type: 'UPDATE_STRATEGY'; strategyId: number; patch: Partial<StrategyConfig> }
  | { type: 'UPDATE_MASTER'; patch: Partial<MasterGateConfig> }
  | { type: 'RESET_STRATEGY'; strategyId: number; defaults: StrategyConfig }
  | { type: 'RESET_ALL'; payload: { master: MasterGateConfig; strategies: Record<string, StrategyConfig> } };
