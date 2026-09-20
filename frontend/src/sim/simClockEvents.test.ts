/** @vitest-environment jsdom */
import { expect, it, vi } from 'vitest';
import { emitSimClockScrub, SIM_CLOCK_SCRUB_EVENT } from './simClockEvents';

it('dispatches a scrub event to window listeners for every seek', () => {
  const listener = vi.fn();
  window.addEventListener(SIM_CLOCK_SCRUB_EVENT, listener);
  try {
    emitSimClockScrub();
    emitSimClockScrub();
    expect(listener).toHaveBeenCalledTimes(2);
    expect(listener.mock.calls[0][0]).toBeInstanceOf(CustomEvent);
    expect(listener.mock.calls[0][0].type).toBe(SIM_CLOCK_SCRUB_EVENT);
  } finally { window.removeEventListener(SIM_CLOCK_SCRUB_EVENT, listener); }
});
