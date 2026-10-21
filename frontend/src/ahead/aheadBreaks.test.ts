import { describe, expect, it } from 'vitest';
import answerReady from './__fixtures__/answer_ready.json';
import { breakOutcome, breakWords, wallBreak } from './aheadBreaks';
import { AHEAD_WORDS } from './aheadConstants';
import { nextWall, type AheadZoneIn } from './aheadGeometry';
import { aheadWalls } from './aheadOdds';
import type { AheadWall } from './aheadTypes';

const wall = (id: string, lo: number, hi: number, up: boolean, label = 'top'): AheadWall =>
  ({ zoneId: id, price: up ? lo : hi, label, lo, hi });
const zone = (id: string, lo: number, hi: number, kind = 'top'): AheadZoneIn =>
  ({ id, lo, hi, label: `${lo} · ${kind}`, members: [{ kind }] });

// The wall above is the zone 4.69-4.72 (a break is a close over 4.72); the next wall above is at 5.00.
const UP = { lo: 4.69, hi: 4.72 };
// The wall below is the zone 4.50-4.56 (a break is a close under 4.50); the next wall below is at 4.30.
const DOWN = { lo: 4.5, hi: 4.56 };

describe('if the wall above breaks', () => {
  it('breaks only past the far edge, then races the next wall against a close back under the near edge', () => {
    expect(breakOutcome([4.62, 4.7, 4.72, 4.65], UP, true, 5)).toBe('none'); // inside the zone, never over its top
    expect(breakOutcome([4.62, 4.73, 4.9, 5.0], UP, true, 5)).toBe('follow'); // at the next wall counts
    expect(breakOutcome([4.62, 4.73, 4.7, 4.68], UP, true, 5)).toBe('fail'); // back in the zone is not a fail yet
    expect(breakOutcome([4.62, 4.73, 4.8, 4.71], UP, true, 5)).toBe('open');
  });

  it('counts a break and its follow-through in the same minute (a gap through both walls)', () => {
    expect(breakOutcome([4.62, 5.05, 4.5], UP, true, 5)).toBe('follow');
  });

  it('with no next wall, races holding over the near edge against a close back under it', () => {
    expect(breakOutcome([4.62, 4.73, 4.69], UP, true, null)).toBe('open'); // at the near edge still holds
    expect(breakOutcome([4.62, 4.73, 4.6], UP, true, null)).toBe('fail');
  });
});

describe('if the wall below breaks', () => {
  it('is the mirror: a close under the low edge breaks, at the next wall below follows, back over the top fails', () => {
    expect(breakOutcome([4.6, 4.5, 4.55], DOWN, false, 4.3)).toBe('none');
    expect(breakOutcome([4.6, 4.49, 4.3], DOWN, false, 4.3)).toBe('follow');
    expect(breakOutcome([4.6, 4.49, 4.57], DOWN, false, 4.3)).toBe('fail');
    expect(breakOutcome([4.6, 4.49, 4.45], DOWN, false, 4.3)).toBe('open');
    expect(breakOutcome([4.6, 4.2], DOWN, false, 4.3)).toBe('follow');
  });

  it('judges each wall on its own: a close jumping from over the wall above to under the wall below', () => {
    const path = [4.62, 4.75, 4.45, 4.29];
    expect(breakOutcome(path, UP, true, 5)).toBe('fail');
    expect(breakOutcome(path, DOWN, false, 4.3)).toBe('follow');
  });
});

describe('the shares', () => {
  it('gives the break over all paths and the race over the paths that break', () => {
    const paths = [
      [4.73, 5.0], [4.73, 4.6], [4.73, 4.8], [4.73, 5.1], // 2 follow, 1 fail, 1 open
      ...Array.from({ length: 6 }, () => [4.62, 4.63]), // no break
    ];
    const b = wallBreak(paths, wall('w', 4.69, 4.72, true), true, wall('n', 5, 5.05, true));
    expect(b).toMatchObject({ share: 0.4, nBreak: 4, follow: 0.5, fail: 0.25, open: 0.25 });
    expect(b.next?.price).toBe(5);
  });

  it('says nothing about the race when no path breaks, and has no follow-through with no next wall', () => {
    const none = wallBreak([[4.62, 4.63]], wall('w', 4.69, 4.72, true), true, null);
    expect(none).toEqual({ share: 0, nBreak: 0, next: null, follow: null, fail: null, open: null });
    const noNext = wallBreak([[4.73, 4.8], [4.73, 4.6]], wall('w', 4.69, 4.72, true), true, null);
    expect(noNext).toMatchObject({ follow: null, fail: 0.5, open: 0.5 });
  });

  it('finds the next wall beyond each wall, skipping round numbers and zones that overlap it', () => {
    const zones = [zone('w', 4.69, 4.72), zone('over', 4.71, 4.75), zone('half', 4.8, 4.8, 'half'), zone('n', 5, 5.05),
      zone('far', 5.5, 5.6), zone('b', 4.5, 4.56, 'bottom'), zone('nb', 4.3, 4.31, 'bottom')];
    expect(nextWall(zones, wall('w', 4.69, 4.72, true), true)?.zoneId).toBe('n');
    expect(nextWall(zones, wall('b', 4.5, 4.56, false), false)).toMatchObject({ zoneId: 'nb', price: 4.31 });
    expect(nextWall(zones, wall('far', 5.5, 5.6, true), true)).toBeNull();
  });
});

describe('the words', () => {
  it("reads like the operator's line, every share marked a forecast", () => {
    const b = { share: 0.38, nBreak: 76, next: wall('n', 5, 5.05, true, 'HOD'), follow: 0.45, fail: 0.4, open: 0.15 };
    const w = breakWords(b, wall('w', 4.69, 4.69, true), true, 200);
    expect(AHEAD_WORDS.breakLine(w)).toBe('If 4.69 · top breaks (38% of paths): 45% reach 5.00 · HOD first, 40% close '
      + 'back under 4.69, 15% still open (forecast)');
    // The chip: a share before each word, never a share beside a price.
    expect(AHEAD_WORDS.breakChip(w)).toBe('breaks 38% · then 45% reach 5.00 · 40% back under');
    expect(AHEAD_WORDS.breakChip(w)).not.toMatch(/\d\.\d\d \d+%/);
  });

  it('names a wide wall by its one name (price and label, as its chip and card), never its zone', () => {
    const b = { share: 0.2, nBreak: 2, next: null, follow: null, fail: 0.5, open: 0.5 };
    const w = breakWords(b, wall('b', 4.55, 4.56, false, 'double bottom · VWAP'), false, 10);
    expect(w.wall).toBe(AHEAD_WORDS.wallName('4.56', 'double bottom · VWAP'));
    expect(AHEAD_WORDS.breakLine(w)).toBe('If 4.56 · double bottom · VWAP breaks (20% of paths): 50% hold under 4.56, '
      + '50% close back over 4.56 (forecast) · no next wall below within reach');
    expect(AHEAD_WORDS.breakLine(w)).not.toContain('4.55');
    expect(AHEAD_WORDS.breakChip(w)).toBe('breaks 20% · then 50% hold · 50% back over');
  });

  it('says when no path breaks, and names a wall with no label by its price alone', () => {
    const b = { share: 0, nBreak: 0, next: null, follow: null, fail: null, open: null };
    const none = breakWords(b, wall('b', 4.5, 4.5, false, ''), false, 10);
    expect(AHEAD_WORDS.breakLine(none)).toBe('If 4.50 breaks (0% of paths): none of the 10 paths closes past it (forecast).');
    expect(AHEAD_WORDS.breakChip(none)).toBe('breaks 0%');
  });
});

describe("the fixture's paths", () => {
  const paths = answerReady.ai.paths.close as number[][];
  const zones = [zone('up', 4.66, 4.68), zone('next', 4.72, 4.73), zone('down', 4.56, 4.57, 'bottom'),
    zone('nextDown', 4.5, 4.51, 'bottom')];

  /** The same rule written out a second way: per path, every minute from the first close past the far edge. */
  function reference(up: boolean, far: number, near: number, next: number) {
    let n = 0;
    const o = { follow: 0, fail: 0, open: 0 };
    for (const p of paths) {
      const k = p.findIndex((c) => (up ? c > far : c < far));
      if (k < 0) continue;
      n += 1;
      const rest = p.slice(k);
      const hit = rest.findIndex((c) => (up ? c >= next : c <= next));
      const back = rest.findIndex((c) => (up ? c < near : c > near));
      if (hit >= 0 && (back < 0 || hit <= back)) o.follow += 1;
      else if (back >= 0) o.fail += 1;
      else o.open += 1;
    }
    return { n, ...o };
  }

  it('carries breaks under both walls, matching the rule worked out a second way', () => {
    const w = aheadWalls(zones, answerReady.price, paths, answerReady.as_of);
    const above = w.breaks?.above;
    const below = w.breaks?.below;
    expect(above?.next?.zoneId).toBe('next');
    expect(below?.next?.zoneId).toBe('nextDown');
    const ra = reference(true, 4.68, 4.66, 4.72);
    const rb = reference(false, 4.56, 4.57, 4.51);
    expect(above?.nBreak).toBe(ra.n);
    expect(below?.nBreak).toBe(rb.n);
    expect(ra.n + rb.n).toBeGreaterThan(0);
    for (const [b, r] of [[above, ra], [below, rb]] as const) {
      if (!b || r.n === 0) continue;
      expect(b.follow).toBeCloseTo(r.follow / r.n);
      expect(b.fail).toBeCloseTo(r.fail / r.n);
      expect(b.open).toBeCloseTo(r.open / r.n);
      expect((b.follow ?? 0) + (b.fail ?? 0) + (b.open ?? 0)).toBeCloseTo(1);
    }
  });

  it('has no breaks without paths (the AI view not shown)', () => {
    expect(aheadWalls(zones, answerReady.price, null, answerReady.as_of).breaks).toBeNull();
  });
});
