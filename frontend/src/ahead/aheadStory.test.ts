import { describe, expect, it } from 'vitest';
import { AHEAD_COLORS, AHEAD_STORY_ALPHA, AHEAD_WORDS } from './aheadConstants';
import { caseStory, crossingStep, stages, strategyStory, typicalMember } from './aheadStory';

// Nova Marketing Sample Data: made-up closes, the numbers mean nothing.
const START = 4.62;
const LV = { trigger: 4.7, stop: 4.55, target: 4.84 };
const A = [4.66, 4.74, 4.8, 4.86, 4.88]; // fills, then reaches the target
const B = [4.5, 4.4, 4.72, 4.86, 4.9]; // dives under the stop BEFORE it fills, then reaches the target
const C = [4.65, 4.75, 4.82, 4.85, 4.87]; // fills, then reaches the target
const D = [4.68, 4.72, 4.6, 4.54, 4.5]; // fills, then the stop
const E = [4.6, 4.72, 4.75, 4.74, 4.73]; // fills, still open
const F = [4.6, 4.58, 4.6, 4.62, 4.61]; // never fills
const story = (paths: number[][]) => strategyStory(paths, START, LV.trigger, LV.stop, LV.target);

describe('where a path crosses a level', () => {
  it('interpolates between the two whole steps, from the start price before step 1', () => {
    expect(crossingStep([4.6, 4.8], START, 1, 4.7)).toBeCloseTo(1.5);
    expect(crossingStep([4.8], 4.6, 0, 4.7)).toBeCloseTo(0.5);
    // A gap past the level lands on the step it closed on, never before the step it came from.
    expect(crossingStep([4.6, 4.6], START, 1, 4.7)).toBe(2);
    expect(crossingStep([4.9], 4.8, 0, 4.7)).toBe(0);
  });
});

describe('the most typical member of a group', () => {
  it("is the path nearest the group's per-step median", () => {
    expect(typicalMember([A, B, C], [0, 1, 2])).toBe(0);
    expect(typicalMember([A, B, C, E], [1, 2, 3])).toBe(2); // the dive (B) is never the typical one
    expect(typicalMember([A, B, C], [2])).toBe(2);
  });
});

describe('the stages of a story path', () => {
  it('runs grey to the start, coloured to the end, faded after, end to end; grey throughout with no start', () => {
    expect(stages(15, '#0f0', 2.5, 7.25)).toEqual([
      { from: 0, to: 2.5, color: AHEAD_COLORS.muted, alpha: AHEAD_STORY_ALPHA.before },
      { from: 2.5, to: 7.25, color: '#0f0', alpha: AHEAD_STORY_ALPHA.during },
      { from: 7.25, to: 15, color: '#0f0', alpha: AHEAD_STORY_ALPHA.after },
    ]);
    expect(stages(15, '#0f0', 3, null)).toEqual([
      { from: 0, to: 3, color: AHEAD_COLORS.muted, alpha: AHEAD_STORY_ALPHA.before },
      { from: 3, to: 15, color: '#0f0', alpha: AHEAD_STORY_ALPHA.during },
    ]);
    expect(stages(15, '#0f0', null, null)).toEqual([
      { from: 0, to: 15, color: AHEAD_COLORS.muted, alpha: AHEAD_STORY_ALPHA.before },
    ]);
    // A fill on the anchor leaves no grey stretch.
    expect(stages(15, '#0f0', 0, 4)[0]).toMatchObject({ from: 0, to: 4, color: '#0f0' });
  });
});

describe("a strategy's story paths", () => {
  it("draws one per outcome group -- target, stop, still open -- each its group's most typical member", () => {
    const s = story([A, B, C, D, E, F]);
    expect(s.map((x) => x.points)).toEqual([A, D, E]);
    // Of the 5 paths that fill: 3 target first, 1 stop first, 1 still open.
    expect(s.map((x) => x.label)).toEqual([AHEAD_WORDS.storyTarget(0.6), AHEAD_WORDS.storyStop(0.2),
      AHEAD_WORDS.storyOpen(0.2)]);
    // Each says what its share is of: the paths that fill.
    expect(s.map((x) => x.label)).toEqual(['✓ target first · 60% of fills (forecast)',
      '✕ stop first · 20% of fills (forecast)', 'still open · 20% of fills (forecast)']);
    expect(s.map((x) => x.short)).toEqual(['✓ target first · 60% of fills', '✕ stop first · 20% of fills',
      'still open · 20% of fills']);
    expect(s.map((x) => x.tiny)).toEqual(['✓ 60% of fills', '✕ 20% of fills', 'open 20% of fills']);
    expect(s.map((x) => x.color)).toEqual([AHEAD_COLORS.target, AHEAD_COLORS.stop, AHEAD_COLORS.path]);
  });

  it('is grey before the fill, coloured from the fill to the exit, faded after, the crossings between steps', () => {
    const [a] = story([A]);
    const fill = 1.5; // 4.66 -> 4.74 crosses the buy-stop 4.70 half way into step 2
    const exit = 3 + 0.04 / 0.06; // 4.80 -> 4.86 crosses the target 4.84
    expect(a.segments).toHaveLength(3);
    expect(a.segments[0]).toMatchObject({ from: 0, color: AHEAD_COLORS.muted, alpha: AHEAD_STORY_ALPHA.before });
    expect(a.segments[0].to).toBeCloseTo(fill);
    expect(a.segments[1]).toMatchObject({ color: AHEAD_COLORS.target, alpha: AHEAD_STORY_ALPHA.during });
    expect(a.segments[1].to).toBeCloseTo(exit);
    expect(a.segments[2]).toMatchObject({ to: 5, color: AHEAD_COLORS.target, alpha: AHEAD_STORY_ALPHA.after });
    expect(a.marks.map((m) => m.kind)).toEqual(['fill', 'target']);
    expect(a.marks[0]).toMatchObject({ p: 4.7, color: AHEAD_COLORS.trigger });
    expect(a.marks[0].k).toBeCloseTo(fill);
    expect(a.marks[1]).toMatchObject({ p: 4.84, color: AHEAD_COLORS.target });
    expect(a.marks[1].k).toBeCloseTo(exit);
  });

  it("never colours a dive under the stop before the fill as the trade's: it stays grey", () => {
    const [b] = story([B]);
    const fill = 2 + (4.7 - 4.4) / (4.72 - 4.4);
    expect(b.segments[0]).toMatchObject({ from: 0, color: AHEAD_COLORS.muted });
    expect(b.segments[0].to).toBeCloseTo(fill);
    // The steps under the stop (1 and 2) lie inside the grey stretch.
    expect(b.segments[0].to).toBeGreaterThan(2);
    expect(b.marks.map((m) => m.kind)).toEqual(['fill', 'target']);
  });

  it('marks a stop exit with ✕ and fades after it; an open trade stays coloured to the end with its fill dot only', () => {
    const [d, e] = story([D, E]);
    expect(d.marks.map((m) => m.kind)).toEqual(['fill', 'stop']);
    expect(d.marks[1]).toMatchObject({ p: 4.55, color: AHEAD_COLORS.stop });
    expect(d.marks[1].k).toBeCloseTo(3 + 0.05 / 0.06);
    expect(d.segments.map((x) => x.alpha)).toEqual([AHEAD_STORY_ALPHA.before, AHEAD_STORY_ALPHA.during,
      AHEAD_STORY_ALPHA.after]);
    expect(e.marks.map((m) => m.kind)).toEqual(['fill']);
    expect(e.segments[e.segments.length - 1]).toMatchObject({ to: 5, color: AHEAD_COLORS.path,
      alpha: AHEAD_STORY_ALPHA.during });
  });

  it('draws a never-filled path when no path that fills stays open, and skips empty groups', () => {
    const s = story([A, D, F]);
    expect(s.map((x) => x.points)).toEqual([A, D, F]);
    const never = s[2];
    expect(never.label).toBe(AHEAD_WORDS.storyNever(1 / 3));
    expect(never.marks).toEqual([]);
    expect(never.segments).toEqual([{ from: 0, to: 5, color: AHEAD_COLORS.muted, alpha: AHEAD_STORY_ALPHA.before }]);
    // Only target-first paths: one story path. No path fills: the never group alone, all of the paths.
    expect(story([A, C]).map((x) => x.points)).toEqual([A]);
    expect(story([F]).map((x) => x.label)).toEqual([AHEAD_WORDS.storyNever(1)]);
    expect(story([])).toEqual([]);
  });
});

describe("scope All's story paths", () => {
  // Final closes 4.50 .. 4.60 in a made-up order: the 90% / 50% / 10% ranks are 4.59, 4.55, 4.51.
  const finals = [4.55, 4.5, 4.59, 4.52, 4.6, 4.51, 4.57, 4.53, 4.56, 4.54, 4.58];
  const flatTo = (end: number) => [4.62, 4.6, 4.58, end];

  it('picks the high, middle and low cases by their final close ranks (90%, 50%, 10%)', () => {
    const s = caseStory(finals.map(flatTo), START, null, null);
    expect(s.map((x) => x.points[3])).toEqual([4.59, 4.55, 4.51]);
    expect(s.map((x) => x.label)).toEqual([...AHEAD_WORDS.storyCase]);
    expect(s.map((x) => x.short)).toEqual([...AHEAD_WORDS.storyCaseShort]);
    // No wall drawn: every case stays grey, unmarked.
    for (const x of s) {
      expect(x.segments).toEqual([{ from: 0, to: 4, color: AHEAD_COLORS.muted, alpha: AHEAD_STORY_ALPHA.before }]);
      expect(x.marks).toEqual([]);
      expect(x.color).toBe(AHEAD_COLORS.muted);
    }
  });

  it('colours a case from the first wall it reaches, with a ring there; one that reaches neither stays grey', () => {
    const up = [4.7, 4.8, 4.9]; // reaches the wall above 4.84 between steps 2 and 3
    const mid = [4.62, 4.63, 4.61]; // neither
    const down = [4.58, 4.49, 4.45]; // the wall below 4.50 between steps 1 and 2
    const [high, middle, low] = caseStory([down, mid, up], START, 4.84, 4.5);
    expect(high.points).toBe(up);
    expect(high.color).toBe(AHEAD_COLORS.wallAbove);
    expect(high.segments.map((x) => x.color)).toEqual([AHEAD_COLORS.muted, AHEAD_COLORS.wallAbove]);
    expect(high.segments[0].to).toBeCloseTo(2 + 0.4);
    expect(high.marks).toHaveLength(1);
    expect(high.marks[0]).toMatchObject({ kind: 'wall', p: 4.84, color: AHEAD_COLORS.wallAbove });
    expect(high.marks[0].k).toBeCloseTo(2.4);
    expect(middle.segments).toEqual([{ from: 0, to: 3, color: AHEAD_COLORS.muted, alpha: AHEAD_STORY_ALPHA.before }]);
    expect(middle.marks).toEqual([]);
    expect(low.color).toBe(AHEAD_COLORS.wallBelow);
    expect(low.marks[0].k).toBeCloseTo(1 + 0.08 / 0.09);
  });

  it('never draws one path twice, and nothing with no paths', () => {
    expect(caseStory([flatTo(4.5)], START, null, null)).toHaveLength(1);
    expect(caseStory([], START, null, null)).toEqual([]);
  });
});
