/** GET /api/volume-boost -- derived L1 spike list, not a scanner lease. */

export type VolumeBoostStatus = 'hot' | 'cooling';

export type VolumeBoostRow = {
  symbol: string;
  price: number | null;
  spike_ratio: number | null;
  spike_shares: number | null;
  baseline_shares: number | null;
  baseline_rate: number | null;
  status: VolumeBoostStatus;
  spike_started_ts: number | null;
  age_sec: number | null;
};

export type VolumeBoostView = {
  rev?: string;
  volume_boost: VolumeBoostRow[];
  table_state: 'live' | 'unavailable' | string;
  last_scan: number | null;
  feed_error: string | null;
  watched: number;
  windows?: {
    spike_sec: number;
    baseline_sec: number;
    enter_ratio: number;
    exit_ratio: number;
    top_n: number;
  };
};
