/** Spike age for the Volume boost table. */

export function formatSpikeAge(ageSec: number | null | undefined): string {
  if (ageSec == null || ageSec < 0 || !Number.isFinite(ageSec)) return '--';
  const sec = Math.floor(ageSec);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  return `${hr}h ago`;
}

export function volumeBoostEmptyCopy(opts: {
  feedError?: string | null;
  tableState?: string | null;
}): string {
  if (opts.feedError) return opts.feedError;
  if (opts.tableState === 'unavailable') {
    return 'IBKR is not ready -- Volume boost watches existing L1 only.';
  }
  return 'No exceptional volume-rate spikes on the current L1 watch.';
}
