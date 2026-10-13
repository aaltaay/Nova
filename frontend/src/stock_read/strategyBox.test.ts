/**
 * A setup's plan is its strategy box on the 1-minute pane (operator asks 2026-10-12). Forming, on MNDR's Gap and Go plan
 * at 09:01 (entry 2.91 with the price at 2.24, its zones and lines stretching the pane to target 2 at 3.49): one faint
 * box from the stop to target 1, on the setup's window while that is ahead, else waiting at the right edge. Near or
 * armed, on the same plan at 09:55 ("its making the chart extremely big ... can we do that for the rest of them?"): the
 * same box in full colour after the newest candle, saying where it stands, its prices on the axis. A triggered plan has
 * no box (`triggeredPlan.test.ts`).
 */
import type { Time } from 'lightweight-charts';
import { describe, expect, it } from 'vitest';
import { paneDraw } from './chartShapes';
import { normalizeStockRead } from './normalize';
import { emptyPx, LineRenderer, type Px } from './sceneRender';
import type { LabelRect } from './sceneLabels';
import type { SceneStrategy } from './sceneTypes';
import { apusAt, apusReadWire } from './stockReadFixtures';
import { boxedPlan, formingPlan, strategyOf, strategyWords } from './strategyBox';
import { columnLeft, drawStrategy, fitName, strategySpan, type StrategyPx } from './strategyBoxRender';
import type { SetupLevels, StockPlan, StockRead } from './types';
import type { OrderLevels } from './whoTradesModel';
import { etChartSeconds } from '../tickerChartData';

const LAYERS = {
  setups: true, levels: true, past: true, labels: 'compact' as const, hidden: [] as string[], plan: 'auto' as const,
};
const identity = (sec: number) => sec as Time;
const base = normalizeStockRead(apusReadWire) as StockRead;

/** MNDR's Gap and Go plan at 09:01 (the operator's screenshot), on the fixture's day. */
const gapAndGo: StockPlan = {
  ...base.plan!, setup_type: 'gap_and_go', kind: 'gap_and_go', entry: 2.91, stop: 2.7936, target: 2.99, target2: 3.49,
  trigger: 2.9, window: { start: '09:30', end: '10:00', state: 'before' },
};
const planLevels = (p: StockPlan): OrderLevels => ({
  entry: { price: p.entry!, behind: 'plan' }, stop: { price: p.stop!, behind: 'plan' },
  target: { price: p.target!, behind: 'plan' }, target2: { price: p.target2!, behind: 'plan' },
});
const at901 = apusAt(9, 1);

describe('which plans are only forming', () => {
  it('is a setup plan no setup armed, with nothing but the plan behind its levels', () => {
    expect(formingPlan(gapAndGo, planLevels(gapAndGo))).toBe(true);
    expect(formingPlan({ ...gapAndGo, state: 'armed', provisional: false }, planLevels(gapAndGo))).toBe(false);
    expect(formingPlan({ ...gapAndGo, source: 'manual', state: 'manual' }, planLevels(gapAndGo))).toBe(false);
    // An order at the entry is real: the plan's zones and lines say what stands there.
    const working = { ...planLevels(gapAndGo), entry: { price: 2.91, behind: 'order' as const } };
    expect(formingPlan(gapAndGo, working)).toBe(false);
    expect(formingPlan(null, planLevels(gapAndGo))).toBe(false);
  });

  it('boxes every setup plan with only the plan behind it while forming, near or armed', () => {
    for (const state of ['forming', 'near', 'armed'] as const) {
      expect(boxedPlan({ ...gapAndGo, state }, planLevels(gapAndGo))).toBe(true);
    }
    expect(boxedPlan({ ...gapAndGo, state: 'triggered' }, planLevels(gapAndGo))).toBe(false);
    expect(boxedPlan({ ...gapAndGo, source: 'manual', state: 'manual' }, planLevels(gapAndGo))).toBe(false);
    // An order at the entry, or Nova watching the stop: the zones and lines say what stands there.
    expect(boxedPlan({ ...gapAndGo, state: 'armed' },
      { ...planLevels(gapAndGo), entry: { price: 2.91, behind: 'order' } })).toBe(false);
    expect(boxedPlan({ ...gapAndGo, state: 'triggered' },
      { ...planLevels(gapAndGo), stop: { price: 2.79, behind: 'watched' } })).toBe(false);
    expect(formingPlan({ ...gapAndGo, state: 'armed' }, planLevels(gapAndGo))).toBe(false);
  });
});

/** MNDR's Gap and Go lane once armed: armed at the 09:30 open. */
const mndrSetup = { armed_at: apusAt(9, 30) } as SetupLevels;
const at955 = apusAt(9, 55);

describe('the box once the setup is near or armed', () => {
  it('starts after the newest candle and says since when it armed, and until when while its window is open', () => {
    const armed = { ...gapAndGo, state: 'armed' as const, window: { start: '09:30', end: '10:00', state: 'open' } };
    const s = strategyOf(armed, planLevels(armed), 3.49, at955 as Time, at955, mndrSetup)!;
    expect(s).toMatchObject({ state: 'armed', name: 'GAP AND GO', word: 'armed', startBars: null, endBars: null,
      when: 'since 09:30 · until 10:00', whenWaiting: 'since 09:30 · until 10:00', target2: 3.49 });
    const near = strategyOf({ ...armed, state: 'near', window: null }, planLevels(armed), null, at955 as Time, at955,
      mndrSetup)!;
    expect(near).toMatchObject({ word: 'near', when: 'since 09:30' });
  });

  it("says nothing it does not know without the lane's times", () => {
    const armed = { ...gapAndGo, state: 'armed' as const, window: null };
    expect(strategyOf(armed, planLevels(armed), 3.49, at955 as Time, at955)!.when).toBe('');
  });

  it("names its prices' edge-column words only: the axis carries the prices", () => {
    const s = strategyOf({ ...gapAndGo, state: 'armed' }, planLevels(gapAndGo), 3.49, at955 as Time, at955)!;
    expect(strategyWords(s).map(w => [w.text, w.price, w.style])).toEqual([
      ['T1', 2.99, 'plain'], ['entry', 2.91, 'plain'], ['stop', 2.7936, 'plain'],
    ]);
    const short = strategyOf({ ...gapAndGo, state: 'armed', side: 'short' }, planLevels(gapAndGo), null,
      at955 as Time, at955)!;
    expect(strategyWords(short).map(w => w.text)).toEqual(['T1', 'short', 'stop']);
  });

  it('draws the box in place of the zones and lines, its levels kept as axis tags with no line', () => {
    const setups = base.setups.map(l => (l.series ? { ...l, series: { ...l.series, bars_as_of: at955 } } : l));
    const read: StockRead = { ...base, plan: { ...gapAndGo, state: 'armed', provisional: false }, setups };
    const { scene, lines } = paneDraw(read, { pane: 'full', layers: LAYERS, toTime: identity });
    expect(scene.strategy).toMatchObject({ after: at955, state: 'armed', startBars: null, endBars: null });
    expect(scene.boxes.filter(b => b.t2 === null)).toEqual([]);
    expect(lines.filter(l => ['entry', 'stop', 'target', 'target2'].includes(l.id))
      .map(l => [l.id, l.line, l.title, l.axisLabel])).toEqual([
      ['entry', false, '', true], ['stop', false, '', true], ['target', false, '', true], ['target2', false, '', true],
    ]);
    expect(scene.keepInView).toEqual({ min: 2.7936, max: 2.99 });
    // The 10-second pane draws the same box after its own newest candle, its levels axis tags with no line, so the
    // strategy is named there too; the 5-minute pane draws none of the plan (operator choice 2026-10-13).
    const last = at955 + 40;
    const thin = paneDraw(read, { pane: 'thin', layers: LAYERS, toTime: identity,
      lastBar: { t: last as Time, sec: etChartSeconds(last * 1000) } });
    expect(thin.scene.strategy).toMatchObject({ after: last, state: 'armed', startBars: null, endBars: null,
      name: 'GAP AND GO' });
    expect(thin.lines.map(l => [l.id, l.line, l.width, l.axisLabel, l.title])).toEqual([
      ['entry', false, 1, true, ''], ['stop', false, 1, true, ''], ['target', false, 1, true, ''],
      ['target2', false, 1, true, ''],
    ]);
    expect((thin.scene.words ?? []).filter(w => w.id.startsWith('strategy:')).map(w => w.text))
      .toEqual(['T1', 'entry', 'stop']);
    expect(thin.scene.keepInView).toEqual({ min: 2.7936, max: 2.99 });
    const map = paneDraw(read, { pane: 'map', layers: LAYERS, toTime: identity });
    expect(map.lines.filter(l => ['entry', 'stop', 'target', 'target2'].includes(l.id))).toEqual([]);
    expect(map.scene.strategy ?? null).toBeNull();
  });

  it("draws nothing of a hidden lane's box, not even its axis tags; an order's lines stay", () => {
    const ids = ['entry', 'stop', 'target', 'target2'];
    const armed: StockRead = { ...base, plan: { ...base.plan!, state: 'armed', provisional: false } };
    const last = at955 + 40;
    const lastBar = { t: last as Time, sec: etChartSeconds(last * 1000) };
    const hidden = { ...LAYERS, hidden: ['bull_flag'] };
    for (const pane of ['full', 'thin'] as const) {
      const shown = paneDraw(armed, { pane, layers: LAYERS, toTime: identity, lastBar });
      expect(shown.lines.filter(l => ids.includes(l.id)).map(l => l.id)).toEqual(ids);
      const off = paneDraw(armed, { pane, layers: hidden, toTime: identity, lastBar });
      expect(off.lines.filter(l => ids.includes(l.id))).toEqual([]);
      expect(off.scene.strategy ?? null).toBeNull();
    }
    // An order behind a level is real: hiding the lane never hides what stands in the market.
    const levels = { ...planLevels(armed.plan!), entry: { price: armed.plan!.entry!, behind: 'order' as const } };
    const thin = paneDraw(armed, { pane: 'thin', layers: hidden, toTime: identity, lastBar, levels });
    expect(thin.lines.filter(l => ids.includes(l.id)).map(l => [l.id, l.title])).toEqual([
      ['entry', 'ENTRY · working'], ['stop', 'STOP · plan'], ['target', 'TARGET 1 · plan'], ['target2', 'TARGET 2 · plan'],
    ]);
  });
});

describe("the strategy box's scene", () => {
  it('counts a window still ahead in candles from the newest one, and says when', () => {
    const s = strategyOf(gapAndGo, planLevels(gapAndGo), 3.49, at901 as Time, at901)!;
    expect(s).toMatchObject({
      startBars: 29, endBars: 59, entry: 2.91, stop: 2.7936, target: 2.99, target2: 3.49, side: 'long',
      name: 'GAP AND GO', word: 'strategy', when: '09:30–10:00', whenWaiting: 'from 09:30 →',
    });
  });

  it('starts after the newest candle while its window is open, saying until when', () => {
    const open = { ...gapAndGo, setup_type: 'first_pullback', window: { start: '07:00', end: '11:30', state: 'open' } };
    const s = strategyOf(open, planLevels(open), null, apusAt(8, 15) as Time, apusAt(8, 15))!;
    expect(s).toMatchObject({ startBars: null, endBars: 195, name: 'FIRST PULLBACK', when: 'until 11:30',
      whenWaiting: 'until 11:30', target2: null });
  });

  it("names a short plan's side", () => {
    const short = { ...gapAndGo, setup_type: 'failed_breakout', side: 'short' as const, window: null };
    const s = strategyOf(short, planLevels(short), 2.5, at901 as Time, at901)!;
    expect(s).toMatchObject({ side: 'short', name: 'FAILED BREAKOUT ▼ SHORT', when: '', startBars: null,
      endBars: null });
    expect(strategyWords(s).map(w => w.text)).toEqual(['T1 2.99', 'short 2.91', 'stop 2.79']);
  });

  it("names its prices as the edge column's words, faint and with no line of their own", () => {
    const s = strategyOf(gapAndGo, planLevels(gapAndGo), 3.49, at901 as Time, at901)!;
    expect(strategyWords(s).map(w => ({ text: w.text, price: w.price, style: w.style, valueWhenOff: w.valueWhenOff })))
      .toEqual([
        { text: 'T1 2.99', price: 2.99, style: 'plain', valueWhenOff: false },
        { text: 'entry 2.91', price: 2.91, style: 'plain', valueWhenOff: false },
        { text: 'stop 2.79', price: 2.7936, style: 'plain', valueWhenOff: false },
      ]);
  });

  it('draws the box on the 1-minute pane in place of the zones and plan lines, from the newest candle', () => {
    const setups = base.setups.map(l => (l.series ? { ...l, series: { ...l.series, bars_as_of: at901 } } : l));
    const read: StockRead = { ...base, plan: gapAndGo, setups };
    const { scene, lines } = paneDraw(read, { pane: 'full', layers: LAYERS, toTime: identity });
    expect(scene.strategy).toMatchObject({ after: at901, startBars: 29, endBars: 59, name: 'GAP AND GO' });
    expect(scene.boxes.filter(b => b.t2 === null)).toEqual([]);
    expect(lines.filter(l => ['entry', 'stop', 'target', 'target2'].includes(l.id))).toEqual([]);
    expect(scene.keepInView).toEqual({ min: 2.7936, max: 2.99 });
    expect((scene.words ?? []).map(w => w.id)).toEqual(expect.arrayContaining(['strategy:target', 'strategy:entry',
      'strategy:stop']));
    // The 10-second pane draws the faint box too, its window counted in 10-second candles from its own newest one:
    // 09:01:50 to 09:30 is 169 of them, to 10:00 349 (operator report 2026-10-13: AIXI's forming Gap and Go drew four
    // unnamed dotted lines there -- "for which strategy is this specifically?").
    const last = at901 + 50;
    const thin = paneDraw(read, { pane: 'thin', layers: LAYERS, toTime: identity,
      lastBar: { t: last as Time, sec: etChartSeconds(last * 1000) } });
    expect(thin.scene.strategy).toMatchObject({ after: last, state: 'forming', startBars: 169, endBars: 349,
      name: 'GAP AND GO', when: '09:30–10:00' });
    expect(thin.lines).toEqual([]);
    // The 5-minute pane draws none of it.
    const map = paneDraw(read, { pane: 'map', layers: LAYERS, toTime: identity,
      lastBar: { t: last as Time, sec: etChartSeconds(last * 1000) } });
    expect(map.lines.filter(l => ['entry', 'stop', 'target', 'target2'].includes(l.id))).toEqual([]);
    expect(map.scene.strategy ?? null).toBeNull();
  });
});

const SPAN = { right: 800, inner: 740, minText: 80, wait: 140 };

describe('where the box goes on the pane', () => {
  it('stands on its window when its name fits left of the column, running to the pane edge', () => {
    expect(strategySpan({ ...SPAN, after: 100, start: 300, end: 900 })).toEqual({ x1: 300, x2: 800, waiting: false });
    // A window that ends on the pane ends the box there.
    expect(strategySpan({ ...SPAN, after: 100, start: 300, end: 500 })).toEqual({ x1: 300, x2: 500, waiting: false });
  });

  it('never starts before the newest candle', () => {
    expect(strategySpan({ ...SPAN, after: 100, start: 40, end: null })).toEqual({ x1: 100, x2: 800, waiting: false });
    expect(strategySpan({ ...SPAN, after: 100, start: null, end: null })).toEqual({ x1: 100, x2: 800, waiting: false });
  });

  it("waits at the right edge while its window's start leaves no room for its name", () => {
    expect(strategySpan({ ...SPAN, after: 100, start: 700, end: 1200 })).toEqual({ x1: 600, x2: 800, waiting: true });
    expect(strategySpan({ ...SPAN, after: 100, start: 1100, end: 1500 })).toEqual({ x1: 600, x2: 800, waiting: true });
    // Never over the candles, even when the pane leaves it little room.
    expect(strategySpan({ ...SPAN, after: 680, start: 1100, end: 1500 }).x1).toBe(680);
  });

  it("finds the column's words beside its own", () => {
    const word: LabelRect = { left: 700, top: 95, right: 790, bottom: 109 };
    const elsewhere: LabelRect = { left: 500, top: 300, right: 790, bottom: 314 };
    expect(columnLeft(800, 90, 120, [])).toBe(800 - 6);
    expect(columnLeft(800, 90, 120, [word, elsewhere])).toBe(700 - 6);
  });
});

/** A canvas that records the words it is asked to write and measures six pixels a character. */
function fakeCtx() {
  const texts: { text: string; x: number; y: number }[] = [];
  const ctx = new Proxy({} as Record<string, unknown>, {
    get(target, key: string) {
      if (key === 'measureText') return (text: string) => ({ width: text.length * 6 });
      if (key === 'fillText') return (text: string, x: number, y: number) => texts.push({ text, x, y });
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

const SCENE: SceneStrategy = {
  after: 1 as Time, startBars: 29, endBars: 59, entry: 2.91, stop: 2.79, target: 2.99, target2: 3.49, side: 'long',
  state: 'forming', name: 'GAP AND GO', word: 'strategy', when: '09:30–10:00', whenWaiting: 'from 09:30 →',
};
const ARMED: SceneStrategy = {
  ...SCENE, startBars: null, endBars: null, state: 'armed', word: 'armed', when: 'since 09:30 · until 10:00',
  whenWaiting: 'since 09:30 · until 10:00',
};
const px = (o: Partial<StrategyPx> = {}): StrategyPx => ({
  xAfter: 400, xStart: 1100, xEnd: 1500, bar: 10, yEntry: 150, yStop: 210, yTarget: 110, s: SCENE, ...o,
});

describe('drawing the box', () => {
  it('waits at the edge saying when it starts, with target 2 an arrow over it', () => {
    const { ctx, texts } = fakeCtx();
    drawStrategy(ctx, px(), 800, []);
    expect(texts.map(t => t.text)).toEqual(['GAP AND GO', ' strategy', 'from 09:30 →', '↑ T2 3.49']);
    expect(texts[0].x).toBe(794 - 140 + 6);                               // 140 clear of the pane's edge
    expect(texts[3].y).toBeLessThan(110);                                 // over the box's top (target 1)
  });

  it('stands on its window once that leaves room, saying its hours', () => {
    const { ctx, texts } = fakeCtx();
    drawStrategy(ctx, px({ xStart: 450 }), 800, []);
    expect(texts[0]).toMatchObject({ text: 'GAP AND GO', x: 456 });
    expect(texts[2].text).toBe('09:30–10:00');
  });

  it("drops the word before it cuts the name, where the column's words leave little room", () => {
    const { ctx, texts } = fakeCtx();
    const word: LabelRect = { left: 560, top: 112, right: 790, bottom: 126 };
    drawStrategy(ctx, px({ xStart: 450 }), 800, [word]);
    expect(texts.map(t => t.text)).toEqual(['GAP AND GO', '09:30–10:00', '↑ T2 3.49']);
  });

  it("puts a short's target 2 under the box", () => {
    const { ctx, texts } = fakeCtx();
    const short = { ...SCENE, side: 'short' as const, stop: 3.0, target: 2.8, target2: 2.5 };
    drawStrategy(ctx, px({ s: short, yStop: 100, yTarget: 200 }), 800, []);
    const t2 = texts.find(t => t.text.startsWith('↓ T2'))!;
    expect(t2.y).toBeGreaterThan(200);
  });

  it('says where an armed setup stands beside its name, and when under it', () => {
    const { ctx, texts } = fakeCtx();
    drawStrategy(ctx, px({ s: ARMED, xStart: null, xEnd: null }), 800, []);
    expect(texts.map(t => t.text)).toEqual(['GAP AND GO', ' armed', 'since 09:30 · until 10:00', '↑ T2 3.49']);
    expect(texts[0].x).toBe(400 + 10 * 1.5 + 6);                         // after the newest candle
  });

  it('leads the second line with the word for where it stands when the name leaves it no room', () => {
    const { ctx, texts } = fakeCtx();
    // 87 px of room: the name (60) and " armed" (36) do not fit on one line.
    const word: LabelRect = { left: 520, top: 112, right: 790, bottom: 126 };
    drawStrategy(ctx, px({ s: ARMED, xStart: null, xEnd: null }), 800, [word]);
    expect(texts.slice(0, 2).map(t => t.text)).toEqual(['GAP AND GO', 'armed']);
    expect(texts[2].text.startsWith('since')).toBe(true);
    expect(texts[1].y).toBe(texts[2].y);
    expect(texts[2].x).toBeGreaterThan(texts[1].x);
  });

  it('draws target 2 as a dash across the box while it is in view, an arrow once it is off the pane', () => {
    const inView = fakeCtx();
    drawStrategy(inView.ctx, px({ s: ARMED, xStart: null, xEnd: null, yTarget2: 40 }), 800, [], 400);
    const t2 = inView.texts.find(t => t.text.includes('T2'))!;
    expect(t2.text).toBe('T2 3.49');
    expect(t2.y).toBeLessThan(40);                                         // over its dash
    const off = fakeCtx();
    drawStrategy(off.ctx, px({ s: ARMED, xStart: null, xEnd: null, yTarget2: -30 }), 800, [], 400);
    expect(off.texts.find(t => t.text.includes('T2'))!.text).toBe('↑ T2 3.49');
  });

  it("cuts a short's name before its ▼ SHORT, so the box always says it is a short", () => {
    const six = (t: string) => t.length * 6;
    expect(fitName('BACKSIDE LOWER HIGH ▼ SHORT', 120, six)).toBe('BACKSIDE LO… ▼ SHORT');
    expect(fitName('BACKSIDE LOWER HIGH ▼ SHORT', 200, six)).toBe('BACKSIDE LOWER HIGH ▼ SHORT');
    expect(fitName('FIRST PULLBACK', 120, six)).toBe('FIRST PULLBACK');
  });

  it('is drawn by the pane under the column, and the labels after it keep clear of its words', () => {
    const { ctx } = fakeCtx();
    const words: LabelRect[][] = [];
    const scene: Px = { ...emptyPx(), strategy: px() };
    new LineRenderer(scene, () => {}, rects => words.push(rects)).draw({
      useMediaCoordinateSpace: (draw: (s: unknown) => void) => draw({ context: ctx, mediaSize: { width: 800, height: 400 } }),
    } as never);
    expect(words[0].some(r => r.left === 794 - 140 + 6 && r.top === 116)).toBe(true);
  });
});
