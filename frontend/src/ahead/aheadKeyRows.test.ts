import { describe, expect, it } from 'vitest';
import { AHEAD_COLORS, AHEAD_KEY_ROWS, AHEAD_KEY_TITLE, AHEAD_WORDS } from './aheadConstants';
import { aheadKeySection } from './aheadKeyRows';
import type { AheadScene } from './aheadSceneTypes';

describe("Ahead's section in the chart Key", () => {
  const legend: AheadScene['legend'] = [
    { swatch: 'dash', text: AHEAD_WORDS.legendLines },
    { swatch: 'band', text: AHEAD_WORDS.legendRange },
    { swatch: 'paths', text: AHEAD_WORDS.legendPaths(200), n: 200 },
    { swatch: 'box', text: AHEAD_WORDS.legendVolume },
    { swatch: 'hatch', text: AHEAD_WORDS.legendHatch },
  ];
  const wallChip = (sub?: string): AheadScene['chips'][number] => ({ p: 5, text: '▲ 5.00 first · 27% (forecast)',
    short: '▲ 27%', color: AHEAD_COLORS.wallAbove, role: 'wall', ...(sub ? { sub } : {}) });
  const neither: AheadScene['chips'][number] = { p: 4.9, text: 'neither in 15 min · 30% (forecast)',
    short: 'neither 30%', color: AHEAD_COLORS.muted, role: 'neither' };
  const scene = (over: Partial<Pick<AheadScene, 'legend' | 'meet' | 'chips'>> = {}) =>
    ({ legend, meet: null, chips: [], ...over });

  it("lists the legend's marks with the same swatches and colours, the AI volume marked a forecast", () => {
    const s = aheadKeySection(scene(), true);
    expect(s?.title).toBe(AHEAD_KEY_TITLE);
    expect(s?.rows.map(r => r.swatch)).toEqual(['dash', 'band', 'paths', 'box', 'hatch']);
    expect(s?.rows[0]).toMatchObject({ color: AHEAD_COLORS.resistance, ...AHEAD_KEY_ROWS.dash });
    expect(s?.rows[1].fill).toBe(AHEAD_COLORS.keyBand);
    expect(s?.rows[2].text).toBe(AHEAD_KEY_ROWS.paths.text(200));
    expect(s?.rows[3].text).toContain('(forecast)');
    expect(s?.rows[4]).toMatchObject({ color: AHEAD_COLORS.keyHatchStripe, fill: AHEAD_COLORS.hatch });
  });

  it('gives each row one label: its words never repeat it', () => {
    const s = aheadKeySection(scene({ meet: { steps: 5, p: 5, text: 'lines meet ≈ 09:15', inZone: true },
      chips: [wallChip('breaks 38% · then 45% reach 5.20 · 40% back under'), neither] }), true);
    expect(s?.rows.length).toBeGreaterThan(5);
    for (const r of s?.rows ?? []) expect(r.text.toLowerCase()).not.toContain(r.label.toLowerCase());
    expect(new Set(s?.rows.map(r => r.label)).size).toBe(s?.rows.length);
  });

  it('explains the meet ring, the wall chips and the break line while each is drawn', () => {
    const all = aheadKeySection(scene({ meet: { steps: 5, p: 5, text: 'lines meet ≈ 09:15', inZone: true },
      chips: [wallChip('breaks 38% · then 45% reach 5.20 · 40% back under'), neither] }), true);
    expect(all?.rows.map(r => r.label)).toEqual([AHEAD_KEY_ROWS.dash.label, AHEAD_KEY_ROWS.ring.label,
      AHEAD_KEY_ROWS.band.label, AHEAD_KEY_ROWS.paths.label, AHEAD_KEY_ROWS.box.label, AHEAD_KEY_ROWS.hatch.label,
      AHEAD_KEY_ROWS.wallFirst.label, AHEAD_KEY_ROWS.breaks.label]);
    expect(all?.rows[1]).toMatchObject({ swatch: 'ring', color: AHEAD_COLORS.meetRing });
    expect(all?.rows[6]).toMatchObject({ swatch: 'up', color: AHEAD_COLORS.wallAbove });
    // A meet past the zone has no ring; wall chips without a break line, no break row; a strategy's chips, neither.
    const some = aheadKeySection(scene({ meet: { steps: 15, p: 5, text: 'lines meet past the zone', inZone: false },
      chips: [wallChip(), neither] }), true);
    expect(some?.rows.map(r => r.label)).not.toContain(AHEAD_KEY_ROWS.ring.label);
    expect(some?.rows.map(r => r.label)).toContain(AHEAD_KEY_ROWS.wallFirst.label);
    expect(some?.rows.map(r => r.label)).not.toContain(AHEAD_KEY_ROWS.breaks.label);
    const strategy = aheadKeySection(scene({ chips: [{ p: 5, text: 'target first · 30% (forecast)', short: 'target 30%',
      color: AHEAD_COLORS.target }] }), true);
    expect(strategy?.rows.map(r => r.swatch)).toEqual(['dash', 'band', 'paths', 'box', 'hatch']);
  });

  it('adds nothing while no zone is drawn', () => {
    expect(aheadKeySection(scene(), false)).toBeNull();
    expect(aheadKeySection(scene({ legend: [] }), true)).toBeNull();
  });
});
