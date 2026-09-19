/** Fired when Sim session scrubber moves — charts should refetch bars. */
export const SIM_CLOCK_SCRUB_EVENT = 'nova:sim-clock-scrub';
export const SIM_CHART_REFRESH_MS = 1000;

export function emitSimClockScrub(): void {
  window.dispatchEvent(new CustomEvent(SIM_CLOCK_SCRUB_EVENT));
}
