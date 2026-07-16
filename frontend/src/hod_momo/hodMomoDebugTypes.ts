export interface Counters {
  total_trades_seen: number;
  universe_size: number;
  snaps_populated: number;
  counters: Record<string, number>;
  session_highs_tracked: number;
  fundamentals_queue_depth: number;
}

export interface SymbolInspect {
  symbol: string;
  snap: {
    price: number | null;
    rvol: number | null;
    float_shares: number | null;
    gap_pct: number | null;
    change_pct: number | null;
    volume: number | null;
    fifty_two_week_high: number | null;
    last_enriched: number;
  };
  session_high: number | null;
  decisions: Array<{
    ts: number;
    price: number;
    gate_blocked: string | null;
    strategies: Array<{ id: number; name: string; passed: boolean; blocked_by: string }>;
    would_fire: boolean;
  }>;
  would_fire_now: {
    gate: string;
    strategies: Array<{ id: number; name: string; passed: boolean; blocked_by: string }>;
  } | null;
}
