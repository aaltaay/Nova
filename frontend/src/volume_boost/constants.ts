/** Volume boost tab tunables -- mirrors backend/constants_scanner.py. */

export const VOLUME_BOOST_POLL_MS = 2_000;
export const VOLUME_BOOST_DESCRIPTION =
  'Exceptional last-60s volume rate vs the prior 10 minutes on names already on the L1 watch. Not session RVOL, not Large Cap swing RVOL. Empty means no spike right now.';
export const VOLUME_BOOST_EMPTY =
  'No exceptional volume-rate spikes on the current L1 watch.';
export const VOLUME_BOOST_FEED_DOWN =
  'IBKR is not ready -- Volume boost watches existing L1 only.';
export const VOLUME_BOOST_SAMPLE_NOTE =
  'Sample Data mode -- fixture spikes, not live IBKR volume.';
export const VOLUME_BOOST_COLUMNS: [string, string][] = [
  ['symbol', 'Symbol'],
  ['price', 'Price'],
  ['spike_ratio', 'Spike'],
  ['spike_shares', 'Last 60s'],
  ['age_sec', 'Age'],
  ['status', 'Status'],
];
