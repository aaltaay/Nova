/** Sample HOD Momo alerts + config stub for the isolated sample route. */
import type {
  AlertObject,
  HodMomoConfigState,
  MasterGateConfig,
  StrategyConfig,
} from '../hod_momo/types';

const now = Date.now();

function alert(
  id: string,
  ticker: string,
  strategy_id: number,
  strategy_name: string,
  price: number,
  change_pct: number,
  minsAgo: number,
  extras: Partial<AlertObject> = {},
): AlertObject {
  return {
    id,
    timestamp: new Date(now - minsAgo * 60_000).toISOString(),
    ticker,
    strategy_id,
    strategy_name,
    price,
    change_pct,
    rvol: extras.rvol ?? 12.5,
    rvol_5min: extras.rvol_5min ?? 8.2,
    float_shares: extras.float_shares ?? 4_200_000,
    gap_pct: extras.gap_pct ?? 28,
    volume: extras.volume ?? 9_500_000,
    momentum_pct: extras.momentum_pct ?? 6.4,
    rvol_source: 'sample',
    consolidation_count: extras.consolidation_count ?? 1,
    consolidated_ids: extras.consolidated_ids ?? [id],
    consolidation_span_sec: extras.consolidation_span_sec ?? null,
    created_ts: now / 1000 - minsAgo * 60,
    strategies: extras.strategies,
  };
}

export const SAMPLE_HOD_ALERTS: AlertObject[] = [
  alert('s-hod-1', 'MOMO', 1, 'HOD Break', 3.15, 31.3, 2, {
    consolidation_count: 3,
    consolidated_ids: ['s-hod-1a', 's-hod-1b', 's-hod-1'],
    consolidation_span_sec: 4,
    strategies: [
      { id: 1, name: 'HOD Break' },
      { id: 3, name: '5min Surge' },
    ],
  }),
  alert('s-hod-2', 'SPIK', 3, '5min Surge', 1.45, 52.6, 5, {
    rvol: 28,
    float_shares: 1_200_000,
  }),
  alert('s-hod-3', 'GAPX', 2, 'Premarket HOD', 1.92, 74.5, 8, {
    rvol: 40,
    gap_pct: 74.5,
  }),
  alert('s-hod-4', 'RUNR', 1, 'HOD Break', 6.8, 65.9, 12),
  alert('s-hod-5', 'FLTX', 4, 'Low Float Runner', 0.88, 69.2, 15, {
    float_shares: 900_000,
    rvol: 55,
  }),
  alert('s-hod-6', 'HODX', 3, '5min Surge', 9.2, 31.4, 18),
  alert('s-hod-7', 'SMPL', 1, 'HOD Break', 4.25, 51.8, 22, {
    strategies: [{ id: 1, name: 'HOD Break' }],
  }),
  alert('s-hod-8', 'VLTG', 5, 'Parabolic', 3.9, 25.8, 30),
];

const SAMPLE_MASTER: MasterGateConfig = {
  hod_required: true,
  surge_pct: 3,
  surge_window_min: 5,
  min_rvol: 2,
  premarket_min_rvol: 1,
  afterhours_min_rvol: 1,
  cooldown_sec: 60,
  consolidation_sec: 5,
};

function strat(
  strategy_id: number,
  name: string,
  color: string,
): StrategyConfig {
  return {
    strategy_id: strategy_id as StrategyConfig['strategy_id'],
    name,
    color,
    enabled: true,
    audio: false,
    notes: 'Sample strategy (demo only)',
    min_price: 0.5,
    max_price: 20,
    min_float: 0,
    max_float: 20_000_000,
    min_volume: 100_000,
    min_rvol: 2,
    max_rvol: 100,
    min_gap_pct: 0,
    max_gap_pct: 200,
    min_change_pct: 0,
    max_change_pct: 200,
    surge_pct: 3,
    surge_window_min: 5,
    surge_method: 'low_to_current',
    proximity_52wk_pct: 0,
    former_momo_list: [],
    requires_hod: true,
  };
}

export const SAMPLE_HOD_CONFIG: HodMomoConfigState = {
  master: SAMPLE_MASTER,
  strategies: {
    '1': strat(1, 'HOD Break', '#22c55e'),
    '2': strat(2, 'Premarket HOD', '#3b82f6'),
    '3': strat(3, '5min Surge', '#f59e0b'),
    '4': strat(4, 'Low Float Runner', '#a855f7'),
    '5': strat(5, 'Parabolic', '#ef4444'),
  },
  loaded: true,
};
