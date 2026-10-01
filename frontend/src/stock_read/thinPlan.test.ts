/**
 * A setup plan on a stock too thin to trade (operator decision 2026-10-01, on LPA: "there's no way I will ever
 * trade something like that"): the badge says so instead of the setup's track or its score, the chart draws no
 * plan (no zones, no plan-only lines, its lane faded), and Level 2 marks no plan levels.
 */
import type { Time } from 'lightweight-charts';
import { describe, expect, it } from 'vitest';
import { normalizeLiquidity } from '../setups';
import { paneDraw } from './chartShapes';
import { momentOf } from './momentModel';
import { normalizeStockRead } from './normalize';
import { thinPlan } from './planVerdict';
import { apusReadWire } from './stockReadFixtures';
import type { StockRead } from './types';
import { inputs, pfsaRead } from './whoTradesFixtures';
import { level2Markers, orderLevels } from './whoTradesModel';

const THIN = normalizeLiquidity({
  state: 'thin', reasons: ['traded $999K today, under $2.00M'], failed: ['day'], unknown: {},
  day_dollars: 999_309, pace_dollars: 142_000, pace_sec: 300, walk: null, as_of: 1_790_862_062,
  limits: { day_dollars: 2_000_000, pace_dollars: 100_000, walk_r: 0.25 },
});
const LAYERS = {
  setups: true, levels: true, past: true, labels: 'compact' as const, hidden: [] as string[], plan: 'auto' as const,
};
const identity = (sec: number) => sec as Time;

describe('a setup plan too thin to trade', () => {
  it('reads TOO THIN TO TRADE on the badge, with no track, even once it played out', () => {
    const read = pfsaRead('triggered', { liquidity: THIN,
      result: { outcome: 'stop_first', at: null, r: -1, text: 'the stop printed first' } });
    expect(thinPlan(read.plan)).toBe(true);
    const m = momentOf(inputs({ read }));
    expect(m).toMatchObject({ badge: 'FIRST PULLBACK · TOO THIN TO TRADE', tone: 'thin', track: false });
    expect(m?.call ?? null).toBeNull();                                  // no ENTER NOW on it
  });

  it('marks no plan level in Level 2 and leaves a liquid plan as it was', () => {
    const thin = inputs({ read: pfsaRead('near', { liquidity: THIN }) });
    expect(orderLevels(thin)).toBeNull();
    expect(level2Markers(orderLevels(thin))).toEqual([]);
    const liquid = inputs({ read: pfsaRead('near') });
    expect(level2Markers(orderLevels(liquid)).map(m => m.id)).toEqual(['entry', 'stop', 'target']);
  });

  it('draws no zones and no plan lines on the 1-minute pane, and fades its lane', () => {
    const base = normalizeStockRead(apusReadWire) as StockRead;
    const read: StockRead = { ...base, plan: base.plan ? { ...base.plan, liquidity: THIN } : null };
    const { scene, lines } = paneDraw(read, { pane: 'full', layers: LAYERS, toTime: identity });
    expect(scene.boxes.filter(b => b.t2 === null)).toEqual([]);          // the plan's zones
    expect(lines.filter(l => ['entry', 'stop', 'target'].includes(l.id))).toEqual([]);
    expect(scene.keepInView).toBeNull();
    const liquid = paneDraw(base, { pane: 'full', layers: LAYERS, toTime: identity });
    expect(liquid.scene.boxes.filter(b => b.t2 === null)).toHaveLength(2);
    // The lane is drawn either way -- faded when thin -- so the setup itself stays visible.
    expect(scene.boxes.map(b => b.label)).toContain('POLE +7.1%');
  });
});
