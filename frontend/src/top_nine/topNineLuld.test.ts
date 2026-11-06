import { describe, expect, it } from 'vitest';
import type { LuldTrail } from '../ibkr';
import { etChartSeconds } from '../tickerChartData';
import { TOP_NINE_LULD_NO_TAPE } from './topNineConstants';
import { topNineLuldShape, type LuldScale } from './topNineLuld';

// 2026-10-27 09:30:00 ET (EDT) as epoch seconds.
const OPEN = Date.parse('2026-10-27T13:30:00Z') / 1000;
const OPEN_MIN = etChartSeconds(OPEN * 1000) / 60;

// The chart starts at 09:00 ET, 4 px a minute; prices 12..16 over y 10..170.
const scale: LuldScale = {
  startMin: OPEN_MIN - 30,
  left: 0,
  right: 240,
  slot: 4,
  top: 10,
  bottom: 170,
  yOf: (p) => 10 + ((16 - p) / 4) * 160,
};

function trail(steps: LuldTrail['steps'], extra: Partial<LuldTrail> = {}): LuldTrail {
  return {
    schema_version: 1, symbol: 'AIOK', source: 'live', state: 'bands', reason: null, tier_sure: true,
    watching_since: OPEN, steps, as_of: OPEN + 300, ...extra,
  };
}

describe('topNineLuldShape', () => {
  it('draws each step from its own second, with a join where the band moved, and tags the band in force', () => {
    const shape = topNineLuldShape(trail([
      { ts: OPEN, lower: 12.88, upper: 15.74, exact: true },
      { ts: OPEN + 120, lower: 13.0, upper: 15.9, exact: true },
    ]), scale, null)!;
    expect(shape.none).toBeNull();
    // 09:30 is minute 30 of the chart: x 120; 09:32 x 128; as_of 09:35 x 140.
    expect(shape.pieces).toContainEqual({ x1: 120, y1: scale.yOf(15.74), x2: 128, y2: scale.yOf(15.74), dashed: false });
    expect(shape.pieces).toContainEqual({ x1: 128, y1: scale.yOf(15.9), x2: 140, y2: scale.yOf(15.9), dashed: false });
    expect(shape.pieces).toContainEqual({ x1: 128, y1: scale.yOf(15.74), x2: 128, y2: scale.yOf(15.9), dashed: false });
    expect(shape.tags.map((t) => t.label)).toEqual(['▲ 15.90', '▼ 13.00']);
  });

  it('dashes an approximate band and marks its tags ≈', () => {
    const shape = topNineLuldShape(trail([{ ts: OPEN, lower: 12.88, upper: 15.74, exact: false }]), scale, null)!;
    expect(shape.pieces.every((p) => p.dashed)).toBe(true);
    expect(shape.tags.map((t) => t.label)).toEqual(['▲ ≈15.74', '▼ ≈12.88']);
  });

  it('draws nothing for a halt step, and keeps an out-of-view band as an edge tag', () => {
    const halted = topNineLuldShape(trail([
      { ts: OPEN, lower: 12.88, upper: 15.74, exact: true },
      { ts: OPEN + 60, lower: null, upper: null, exact: true },
    ]), scale, null)!;
    expect(halted.tags).toEqual([]);
    expect(halted.pieces.every((p) => p.x2 <= 124)).toBe(true);

    const far = topNineLuldShape(trail([{ ts: OPEN, lower: 10, upper: 20, exact: true }]), scale, null)!;
    expect(far.pieces).toEqual([]);
    expect(far.tags.map((t) => t.y)).toEqual([scale.top, scale.bottom]);
  });

  it('moves a tag off the last-price tag, to the other side when the edge leaves no room', () => {
    const mid = topNineLuldShape(trail([{ ts: OPEN, lower: 12.88, upper: 15.0, exact: true }]), scale, scale.yOf(15.0))!;
    expect(mid.tags[0].y).toBeCloseTo(scale.yOf(15.0) - 18);
    // Halted on the upper band near the top: the band's tag goes under the price's.
    const top = topNineLuldShape(trail([{ ts: OPEN, lower: 12.88, upper: 15.74, exact: true }]), scale, scale.yOf(15.74))!;
    expect(top.tags[0].y).toBeCloseTo(scale.yOf(15.74) + 18);
  });

  it('says why there is no band', () => {
    const shape = topNineLuldShape(trail([], {
      state: 'unknown',
      reason: "Nova computes the band from this stock's Time & Sales: it holds no tape line for it now",
    }), scale, null)!;
    expect(shape.none?.text).toBe(TOP_NINE_LULD_NO_TAPE);
    expect(shape.none?.why).toContain('holds no tape line');
    expect(topNineLuldShape(null, scale, null)).toBeNull();
  });
});
