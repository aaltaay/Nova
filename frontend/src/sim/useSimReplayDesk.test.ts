/** QA W10: live scanner values stay off a Sim desk that is replaying the past. */
import { describe, expect, it } from 'vitest';
import { isReplayDesk, replayPlayheadSec } from './useSimReplayDesk';

describe('isReplayDesk', () => {
  it('is true on Sim off the live edge, loaded or not', () => {
    expect(isReplayDesk(true, { sim: true, live_edge: false, replay_source: 'historical' })).toBe(true);
    expect(isReplayDesk(true, { sim: true, live_edge: false, replay_source: 'none' })).toBe(true);
  });

  it('is false at the live edge, off Sim, and before the clock answers', () => {
    expect(isReplayDesk(true, { sim: true, live_edge: true })).toBe(false);
    expect(isReplayDesk(false, { sim: false, live_edge: false })).toBe(false);
    expect(isReplayDesk(true, null)).toBe(false);
  });
});

describe('replayPlayheadSec', () => {
  it("is the clock's time in epoch seconds on a replay desk, else null", () => {
    const clock = { sim: true, live_edge: false, sim_time_et: '2026-10-02T10:31:00-04:00' };
    expect(replayPlayheadSec(true, clock)).toBe(Date.UTC(2026, 9, 2, 14, 31) / 1000);
    expect(replayPlayheadSec(true, { ...clock, live_edge: true })).toBeNull();
    expect(replayPlayheadSec(false, clock)).toBeNull();
    expect(replayPlayheadSec(true, { ...clock, sim_time_et: 'not a time' })).toBeNull();
  });
});
