/** Fired when Sim playhead commits; omitted symbol means every Sim consumer. */
export const SIM_CLOCK_SCRUB_EVENT = 'nova:sim-clock-scrub';
export const SIM_CHART_REFRESH_MS = 1000;
export interface SimClockScrubDetail { symbol?: string; minute?: number }
export function emitSimClockScrub(detail?: SimClockScrubDetail): void {
  window.dispatchEvent(new CustomEvent(SIM_CLOCK_SCRUB_EVENT, { detail }));
}
export function matchesSimClockScrub(event: Event, symbol: string): boolean {
  const detail = (event as CustomEvent<SimClockScrubDetail | undefined>).detail;
  return !detail?.symbol || detail.symbol.toUpperCase() === symbol.toUpperCase();
}

/** Clear unsent keyboard seeks before an explicit follow/source command. */
export const SIM_SEEK_CANCEL_EVENT = 'nova:sim-seek-cancel';
export function cancelPendingSimSeek(): void {
  window.dispatchEvent(new Event(SIM_SEEK_CANCEL_EVENT));
}
