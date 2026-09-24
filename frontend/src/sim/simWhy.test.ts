import { describe, expect, it } from 'vitest';
import { SIM_WHY_BUSY, SIM_WHY_CLOCK_PENDING, SIM_WHY_NOT_SIM, SIM_WHY_PICK_DAY } from './simConstants';
import { simBusyWhy, simClockWhy, simReplayWhy, simTickerWhy } from './simWhy';

describe('simWhy: why a Sim control is locked', () => {
  it('names a missing clock and a clock off the Sim venue; a Sim clock is no reason', () => {
    expect(simClockWhy(null)).toBe(SIM_WHY_CLOCK_PENDING);
    expect(simClockWhy({ sim: false })).toBe(SIM_WHY_NOT_SIM);
    expect(simClockWhy({ sim: true })).toBeNull();
  });

  it('names the first request in flight among the keys asked about', () => {
    const busy = new Set(['follow', 'replay']);
    expect(simBusyWhy(busy, ['clock', 'follow'])).toBe(SIM_WHY_BUSY.follow);
    expect(simBusyWhy(busy, ['clock', 'day'])).toBeNull();
    expect(simBusyWhy(new Set(), ['clock', 'follow', 'day'])).toBeNull();
  });

  it('says whether a replay change is a load (of which ticker) or a close', () => {
    expect(simReplayWhy(new Set(['replay']), 'GRML')).toBe('Loading GRML -- wait for it to finish');
    expect(simReplayWhy(new Set(['replay']), '')).toBe('Closing the replay -- wait for it to finish');
    expect(simReplayWhy(new Set(['clock']), 'GRML')).toBeNull();
  });

  it('locks the Ticker picker until a Day is picked, and while a replay changes', () => {
    expect(simTickerWhy(new Set(), '', '')).toBe(SIM_WHY_PICK_DAY);
    expect(simTickerWhy(new Set(), '2026-09-21', '')).toBeNull();
    expect(simTickerWhy(new Set(['replay']), '2026-09-21', 'GRML')).toBe('Loading GRML -- wait for it to finish');
  });
});
