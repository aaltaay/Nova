/** QA W10: live scanner values stay off a Sim desk that is replaying the past. */
import { describe, expect, it } from 'vitest';
import { isReplayDesk } from './useSimReplayDesk';

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
