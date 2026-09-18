import type { VolumeBoostRow, VolumeBoostView } from './types';

export const SAMPLE_VOLUME_BOOST_ROWS: VolumeBoostRow[] = [
  {
    symbol: 'BOOST',
    price: 3.42,
    spike_ratio: 8.4,
    spike_shares: 92_000,
    baseline_shares: 18_000,
    baseline_rate: 30,
    status: 'hot',
    spike_started_ts: 1_000_000,
    age_sec: 14,
  },
  {
    symbol: 'COOL',
    price: 12.08,
    spike_ratio: 3.1,
    spike_shares: 41_000,
    baseline_shares: 22_000,
    baseline_rate: 36.6,
    status: 'cooling',
    spike_started_ts: 999_940,
    age_sec: 74,
  },
];

export const SAMPLE_VOLUME_BOOST_VIEW: VolumeBoostView = {
  rev: 'sample',
  volume_boost: SAMPLE_VOLUME_BOOST_ROWS,
  table_state: 'live',
  last_scan: 1_000_014,
  feed_error: null,
  watched: 24,
};
