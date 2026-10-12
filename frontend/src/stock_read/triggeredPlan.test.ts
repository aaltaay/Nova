/**
 * A setup's plan that triggered with nothing behind it leaves the 1-minute chart (operator ask 2026-10-12, option A of
 * the mockups, on MNDR's Gap and Go box still beside the price at 09:55, 24 minutes after it triggered and 22 after the
 * eyes scored target 1 first): no box, no axis tags, no frame, only a mark over its trigger candle.
 */
import type { Time } from 'lightweight-charts';
import { describe, expect, it } from 'vitest';
import { paneDraw } from './chartShapes';
import { SETUP_COLORS } from './constants';
import { normalizeStockRead } from './normalize';
import { emptyPx, LineRenderer, type LabelHit } from './sceneRender';
import type { SceneMark } from './sceneTypes';
import { apusAt, apusReadWire } from './stockReadFixtures';
import { boxedPlan, strategyOf, triggeredPlan, triggerMark } from './strategyBox';
import type { SetupLane, SetupLevels, StockPlan, StockRead } from './types';
import type { OrderLevels } from './whoTradesModel';

const LAYERS = {
  setups: true, levels: true, past: true, labels: 'compact' as const, hidden: [] as string[], plan: 'auto' as const,
};
const identity = (sec: number) => sec as Time;
const base = normalizeStockRead(apusReadWire) as StockRead;
const BAR = apusAt(15, 2);
const PLAN_IDS = ['entry', 'stop', 'target', 'target2'];
const TOP = Number.MAX_SAFE_INTEGER;

/** APUS's bull flag, triggered at 15:02:20, its plan with nothing behind it. */
const setup = {
  trigger: 5.43, entry: 5.44, stop: 5.33, risk: 0.11, target1: 5.49, target2: 5.99, leg_t: apusAt(15, 1), leg_high: 5.45,
  leg_low: 5.09, armed_at: apusAt(15, 1, 30), triggered_at: apusAt(15, 2, 20),
} as SetupLevels;
const plan: StockPlan = { ...base.plan!, state: 'triggered', provisional: false };
const read: StockRead = {
  ...base, plan,
  setups: base.setups.map(l => (l.setup_type === 'bull_flag' ? { ...l, state: 'triggered', setup } as SetupLane : l)),
};
const planLevels = (p: StockPlan): OrderLevels => ({
  entry: { price: p.entry!, behind: 'plan' }, stop: { price: p.stop!, behind: 'plan' },
  target: { price: p.target!, behind: 'plan' }, target2: { price: p.target2!, behind: 'plan' },
});
const highAt = (sec: number) => (sec === BAR ? 5.47 : null);

describe('which plans leave the chart once triggered', () => {
  it('is a setup plan triggered with nothing but the plan behind its levels', () => {
    expect(triggeredPlan(plan, planLevels(plan))).toBe(true);
    expect(boxedPlan(plan, planLevels(plan))).toBe(false);
    expect(strategyOf(plan, planLevels(plan), 5.99, BAR as Time, BAR, setup)).toBeNull();
    expect(triggeredPlan({ ...plan, state: 'armed' }, planLevels(plan))).toBe(false);
    expect(triggeredPlan({ ...plan, source: 'manual', state: 'manual' }, planLevels(plan))).toBe(false);
    // An order at the entry, or Nova watching the stop: it is a trade, and its zones and lines say so.
    expect(triggeredPlan(plan, { ...planLevels(plan), entry: { price: 5.44, behind: 'order' } })).toBe(false);
    expect(triggeredPlan(plan, { ...planLevels(plan), stop: { price: 5.33, behind: 'watched' } })).toBe(false);
  });
});

describe('a triggered plan on the panes', () => {
  it('leaves the 1-minute pane: no box, no zones, no lines, no frame, a mark over its trigger candle', () => {
    const { scene, lines } = paneDraw(read, { pane: 'full', layers: LAYERS, toTime: identity, highAt });
    expect(scene.strategy ?? null).toBeNull();
    expect(scene.boxes.filter(b => b.t2 === null)).toEqual([]);
    expect(lines.filter(l => PLAN_IDS.includes(l.id))).toEqual([]);
    expect(scene.keepInView).toBeNull();
    expect((scene.words ?? []).filter(w => w.id.startsWith('strategy:'))).toEqual([]);
    expect(scene.marks).toContainEqual({
      t: BAR, price: 5.47, color: SETUP_COLORS.trigger, rank: TOP, dir: 'up', label: '✓ BULL FLAG 15:02',
      shrink: { short: '✓ 15:02', icon: '✓', rank: TOP }, hoverId: 'lane:bull_flag',
    });
  });

  it('keeps its thin lines on the 5-minute and 10-second panes', () => {
    for (const pane of ['map', 'thin'] as const) {
      const { lines } = paneDraw(read, { pane, layers: LAYERS, toTime: identity, highAt });
      expect(lines.filter(l => PLAN_IDS.includes(l.id)).map(l => [l.id, l.width, l.line])).toEqual([
        ['entry', 1, undefined], ['stop', 1, undefined], ['target', 1, undefined], ['target2', 1, undefined],
      ]);
    }
  });

  it('draws the zones and lines once an order stands behind it, and no mark', () => {
    const levels = { ...planLevels(plan), entry: { price: 5.44, behind: 'order' as const } };
    const { scene, lines } = paneDraw(read, { pane: 'full', layers: LAYERS, toTime: identity, highAt, levels });
    expect(scene.boxes.filter(b => b.t2 === null)).toHaveLength(2);
    expect(lines.find(l => l.id === 'entry')).toMatchObject({ style: 'solid', width: 2 });
    expect((scene.marks ?? []).filter(m => m.hoverId === 'lane:bull_flag')).toEqual([]);
  });

  it("leaves the candle to the flat top's own break mark when it entered on the break", () => {
    const flat = {
      ...setup, detail: { entry_mode: 'break', level: 5.42 },
    } as SetupLevels;
    const lane = {
      ...base.setups.find(l => l.setup_type === 'flat_top_breakout')!, state: 'triggered', setup: flat,
      leg: { t: apusAt(14, 50), high: 5.42, low: 5.2, pct: 0.04, bars: 6 },
    } as SetupLane;
    const flatRead: StockRead = {
      ...base, plan: { ...plan, setup_type: 'flat_top_breakout', kind: 'flat_top_breakout' },
      setups: base.setups.map(l => (l.setup_type === 'flat_top_breakout' ? lane : l)),
    };
    const { scene } = paneDraw(flatRead, { pane: 'full', layers: LAYERS, toTime: identity, highAt });
    expect((scene.marks ?? []).filter(m => m.t === BAR).map(m => m.label)).toEqual(['break']);
  });

  it('marks nothing it does not know, and still leaves the pane', () => {
    const noTime = { ...read, setups: read.setups.map(l => (l.setup_type === 'bull_flag'
      ? { ...l, setup: { ...setup, triggered_at: undefined } } : l)) };
    const { scene, lines } = paneDraw(noTime, { pane: 'full', layers: LAYERS, toTime: identity, highAt });
    expect((scene.marks ?? []).filter(m => m.hoverId === 'lane:bull_flag')).toEqual([]);
    expect(lines.filter(l => PLAN_IDS.includes(l.id))).toEqual([]);
    expect(triggerMark(plan, setup, { toTime: () => null }, 'lane:bull_flag')).toBeNull();
  });
});

describe("the trigger's mark", () => {
  it("points down over a short's candle and names the side; without the candle's high it sits at the trigger", () => {
    const short = { ...plan, setup_type: 'failed_breakout', side: 'short' as const };
    expect(triggerMark(short, setup, { toTime: identity }, 'lane:failed_breakout')).toMatchObject({
      dir: 'down', price: 5.43, label: '✓ FAILED BREAKOUT ▼ SHORT 15:02',
    });
  });

  it('says ✓ alone while the labels are compact and the whole label in full, hovered as its setup', () => {
    const m = triggerMark(plan, setup, { toTime: identity, highAt }, 'lane:bull_flag') as SceneMark;
    for (const [labels, text] of [['compact', '✓'], ['full', '✓ BULL FLAG 15:02']] as const) {
      const { ctx, texts } = fakeCtx();
      const hits: LabelHit[][] = [];
      new LineRenderer({ ...emptyPx(), labels, marks: [{ x: 400, y: 200, m }] }, h => hits.push(h)).draw({
        useMediaCoordinateSpace: (draw: (s: unknown) => void) => draw({ context: ctx, mediaSize: { width: 800, height: 400 } }),
      } as never);
      expect(texts).toContain(text);
      expect(hits[0].map(h => h.hoverId)).toEqual(['lane:bull_flag']);
    }
  });
});

function fakeCtx() {
  const texts: string[] = [];
  const ctx = new Proxy({} as Record<string, unknown>, {
    get(target, key: string) {
      if (key === 'measureText') return (text: string) => ({ width: text.length * 6 });
      if (key === 'fillText') return (text: string) => texts.push(text);
      if (key in target) return target[key];
      return () => {};
    },
    set(target, key: string, value) {
      target[key] = value;
      return true;
    },
  });
  return { ctx: ctx as unknown as CanvasRenderingContext2D, texts };
}
