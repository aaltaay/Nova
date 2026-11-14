/**
 * A plan that sells in two halves (#845): Level 2 marks target 2 as T2, and the 1-minute pane frames the stop to the
 * furthest target -- on PFSA's first pullback of 2026-09-24 with a target 2 at 4.80.
 */
import { describe, expect, it } from 'vitest';
import { paneDraw } from './chartShapes';
import { inputs, pfsaRead } from './momentFixtures';
import { planFrame } from './planMath';
import { level2Markers, orderLevels } from './tradeLevels';
import type { StockPlan } from './types';

const HALVES: Partial<StockPlan> = { target2: 4.80, target1_fraction: 0.5 };

describe('Level 2 marks target 2', () => {
  it("marks a plan's target 2 the way it marks target 1, labelled T2", () => {
    const lv = orderLevels(inputs({ read: pfsaRead('armed', HALVES) }));
    expect(lv?.target2).toEqual({ price: 4.80, behind: 'plan' });
    expect(level2Markers(lv).map(m => [m.id, m.label, m.working, m.rests])).toEqual([
      ['entry', 'ENTRY 4.27', false, 'bid'], ['stop', 'STOP 4.14', false, 'bid'],
      ['target', 'TARGET 4.52', false, 'ask'], ['target2', 'T2 4.80', false, 'ask'],
    ]);
    // A short's covers sit under the price with the bids.
    const short = level2Markers({ ...lv!, target: { price: 3.99, behind: 'plan' }, target2: { price: 3.80, behind: 'plan' } },
      'short');
    expect(short.slice(2).map(m => [m.label, m.rests])).toEqual([['TARGET ↓ 3.99', 'bid'], ['T2 ↓ 3.80', 'bid']]);
  });
});

describe('the 1-minute pane frames both targets', () => {
  const LAYERS = { eyes: true, setups: true, levels: false, past: false, labels: 'compact', hidden: [], plan: 'auto' } as const;

  it('frames the stop to the furthest target, the mirror for a short', () => {
    expect(planFrame(4.14, 4.52, 4.80)).toEqual({ min: 4.14, max: 4.80 });
    expect(planFrame(4.14, 4.52, null)).toEqual({ min: 4.14, max: 4.52 });
    expect(planFrame(4.38, 3.99, 3.80)).toEqual({ min: 3.80, max: 4.38 });
    expect(planFrame(null, 4.52, 4.80)).toBeNull();
  });

  it("frames a plan alone to target 1: its box shows target 2, and the axis keeps target 2's tag", () => {
    // Operator ask 2026-10-12: a setup's plan with nothing behind it is its strategy box, never a frame to target 2.
    const read = pfsaRead('armed', HALVES);
    const draw = paneDraw(read, { pane: 'full', layers: { ...LAYERS, hidden: [] }, toTime: t => t as never });
    expect(draw.scene.keepInView).toEqual({ min: 4.14, max: 4.52 });
    expect(draw.scene.strategy).toMatchObject({ target: 4.52, target2: 4.80 });
    const t2 = draw.lines.find(l => l.id === 'target2');
    expect(t2).toMatchObject({ price: 4.80, title: '', axisLabel: true, line: false });
    const one = paneDraw(pfsaRead('armed'), { pane: 'full', layers: { ...LAYERS, hidden: [] }, toTime: t => t as never });
    expect(one.scene.keepInView).toEqual({ min: 4.14, max: 4.52 });
  });
});
