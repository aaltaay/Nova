/** Fired when Sim session scrubber moves — charts should refetch bars. */
export const SIM_CLOCK_SCRUB_EVENT = 'nova:sim-clock-scrub';

export function emitSimClockScrub(): void {
  window.dispatchEvent(new CustomEvent(SIM_CLOCK_SCRUB_EVENT));
}
