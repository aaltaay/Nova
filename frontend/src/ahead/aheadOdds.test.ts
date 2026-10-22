import { describe, expect, it } from 'vitest';
import { AHEAD_WORDS } from './aheadConstants';
import {
  aheadWalls, ifTriggers, pathOutcome, pathTrade, triggerRead, wallFirst, wallTouch, type AheadLaneIn, type AheadReadIn,
} from './aheadOdds';

const flat = (p: number, n = 15) => Array.from({ length: n }, () => p);

describe('which wall first', () => {
  it('counts the first minute close at or past each wall', () => {
    const paths = [
      [4.7, 4.85, 4.4], // above first
      [4.6, 4.5, 4.9], // below first
      flat(4.62), // neither
      [4.84], // at the wall counts
    ];
    expect(wallFirst(paths, 4.84, 4.5)).toEqual({ above: 0.5, below: 0.25, neither: 0.25 });
  });

  it('says which wall one path reaches first and where', () => {
    expect(wallTouch([4.7, 4.85, 4.4], 4.84, 4.5)).toEqual({ side: 'above', at: 1 });
    expect(wallTouch([4.6, 4.5], 4.84, 4.5)).toEqual({ side: 'below', at: 1 });
    expect(wallTouch(flat(4.62), 4.84, 4.5)).toEqual({ side: null, at: -1 });
  });

  it('works with one wall, and has nothing to say with none', () => {
    expect(wallFirst([flat(4.6), [4.9]], 4.84, null)).toEqual({ above: 0.5, below: null, neither: 0.5 });
    expect(wallFirst([flat(4.6)], null, null)).toBeNull();
  });

  it('carries the walls without odds until there are paths, and the time it counts to', () => {
    const zones = [{ id: 'a', lo: 4.84, hi: 4.85, label: 'top', members: [{ kind: 'top' }] }];
    const none = aheadWalls(zones, 4.62, null, 1000);
    expect(none.above?.price).toBe(4.84);
    expect(none.first).toBeNull();
    expect(none.byT).toBe(1000 + 900);
    expect(aheadWalls(zones, 4.62, [[4.9]], 1000).first?.above).toBe(1);
  });
});

describe('if it triggers', () => {
  it('fills on the first close over the trigger and races target and stop from the fill minute on', () => {
    expect(pathOutcome([4.6, 4.65, 4.69], 4.7, 4.55, 4.84)).toBe('no');
    expect(pathOutcome([4.6, 4.71, 4.8, 4.84], 4.7, 4.55, 4.84)).toBe('target');
    expect(pathOutcome([4.6, 4.71, 4.6, 4.55], 4.7, 4.55, 4.84)).toBe('stop');
    expect(pathOutcome([4.6, 4.71, 4.75], 4.7, 4.55, 4.84)).toBe('open');
    expect(pathOutcome([4.7, 4.7], 4.7, 4.55, 4.84)).toBe('no'); // at the trigger is not over it
  });

  it('counts a gap through the target on the fill minute as target first', () => {
    expect(pathOutcome([4.6, 4.9, 4.5], 4.7, 4.55, 4.84)).toBe('target');
  });

  it('says at which step index a path fills and exits (the story paths read the same rule)', () => {
    expect(pathTrade([4.6, 4.71, 4.8, 4.84], 4.7, 4.55, 4.84)).toEqual({ outcome: 'target', fill: 1, exit: 3 });
    expect(pathTrade([4.6, 4.9, 4.5], 4.7, 4.55, 4.84)).toEqual({ outcome: 'target', fill: 1, exit: 1 });
    expect(pathTrade([4.71, 4.75], 4.7, 4.55, 4.84)).toEqual({ outcome: 'open', fill: 0, exit: -1 });
    expect(pathTrade([4.6], 4.7, 4.55, 4.84)).toEqual({ outcome: 'no', fill: -1, exit: -1 });
  });

  it('gives shares of all paths for the reach and of the filled ones for the race', () => {
    const paths = [
      [4.71, 4.9], [4.71, 4.5], [4.71, 4.75], [4.71, 4.85], ...Array.from({ length: 16 }, () => flat(4.6)),
    ];
    const odds = ifTriggers(paths, 4.7, 4.55, 4.84);
    expect(odds.nReach).toBe(4);
    expect(odds.reach).toBe(0.2);
    expect(odds.first).toEqual({ target: 0.5, stop: 0.25, open: 0.25 });
    expect(Object.keys(odds)).toEqual(['nReach', 'reach', 'first']);
    expect(ifTriggers([flat(4.6)], 4.7, 4.55, 4.84).first).toBeNull();
  });
});

describe('the setup in play', () => {
  const lv = (trigger: number) => ({ trigger, entry: trigger + 0.01, stop: trigger - 0.15, target1: trigger + 0.14 });
  const lane = (over: Partial<AheadLaneIn>): AheadLaneIn => ({
    setup_type: 'flat_top_breakout', state: 'armed', setup: lv(4.7), forming: null, ...over,
  });
  const read = (setups: AheadLaneIn[], followed = true): AheadReadIn => ({ followed, followed_note: null, setups });

  it('ranks armed over near over forming, and a tie by the trigger nearest the price', () => {
    const t = triggerRead(read([
      lane({ state: 'near', setup: lv(4.65) }),
      lane({ state: 'leg', setup: null, forming: lv(4.63) }),
      lane({ setup_type: 'second_flat_top_breakout', setup: lv(5.2) }),
      lane({ setup: lv(4.8) }),
    ]), 'flat_top', 4.62, null);
    expect([t.state, t.trigger, t.setupType]).toEqual(['armed', 4.8, 'flat_top_breakout']);
    expect(t.reach).toBeNull();
  });

  it('reads a forming setup as provisional from its forming levels', () => {
    const t = triggerRead(read([lane({ state: 'pullback', setup: null, forming: lv(4.7) })]), 'flat_top', 4.62, null);
    expect(t.state).toBe('forming');
    expect(t.provisional).toBe(true);
    expect(t.target).toBeCloseTo(4.84);
  });

  it('leaves out short, 5-minute, failed and other families, and says so', () => {
    const t = triggerRead(read([
      lane({ side: 'short' }), lane({ timeframe: '5m' }), lane({ state: 'failed' }),
      lane({ setup_type: 'first_pullback' }), lane({ state: 'leg', setup: null, forming: null }),
    ]), 'flat_top', 4.62, null);
    expect(t.reason).toBe(AHEAD_WORDS.noLane('flat top'));
  });

  it('says a triggered setup is followed by the plan card, with no odds', () => {
    const t = triggerRead(read([lane({ state: 'triggered', setup: { ...lv(4.7), triggered_at: Date.UTC(2026, 9, 21, 13, 5) / 1000 } })]),
      'flat_top', 4.62, [flat(4.9)]);
    expect(t.reason).toBe(AHEAD_WORDS.triggered('09:05'));
    expect(t.reach).toBeNull();
  });

  it("says Nova is not watching an unfollowed stock's setups", () => {
    expect(triggerRead(read([lane({})], false), 'flat_top', 4.62, null).reason).toBe(AHEAD_WORDS.notFollowed);
    const noted = { ...read([], false), followed_note: 'Follow it to read its setups' };
    expect(triggerRead(noted, 'first_pullback', 4.62, null).reason).toBe('Follow it to read its setups');
  });

  it('works out the odds from the paths when given them', () => {
    const t = triggerRead(read([lane({})]), 'flat_top', 4.62, [[4.71, 4.9], flat(4.6)]);
    expect(t.reach).toBe(0.5);
    expect(t.first).toEqual({ target: 1, stop: 0, open: 0 });
    expect(t).not.toHaveProperty('perPath');
  });
});
