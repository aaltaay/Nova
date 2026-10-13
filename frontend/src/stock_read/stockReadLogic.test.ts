import type { Time } from 'lightweight-charts';
import { describe, expect, it } from 'vitest';
import { laneChip, paneDraw, paneKind, planBadgeText } from './chartShapes';
import { normalizeHistory } from './historyNormalize';
import { normalizeDecisions, normalizeStockRead } from './normalize';
import {
  fmtPx,
  fmtStep,
  formingProgress,
  planBadgeShort,
  planBadge,
  planFootnote,
  planLane,
  planSubLines,
  planTargetWords,
  placeRulerLabels,
  rrText,
  rulerLayout,
  sizeFor,
  stopCap,
} from './planMath';
import { parseRiskUsd } from '../setups';
import { historySummary } from './HistoryTab';
import { tileValue } from './ReadStrip';
import { readSummary } from './SignalsTab';
import { eventTone } from './DecisionsTab';
import { apusAt, apusDecisionsWire, apusHistoryWire, apusReadWire } from './stockReadFixtures';
import type { StockRead } from './types';
import { draggedPlan } from './usePlanDrag';

const LAYERS = {
  setups: true, levels: true, past: true, labels: 'compact' as const, hidden: [] as string[], plan: 'auto' as const,
};
const read = normalizeStockRead(apusReadWire) as StockRead;
/** Every minute maps onto itself: a pane whose bars cover the day. */
const identity = (sec: number) => sec as Time;

describe('normalizeStockRead', () => {
  it('reads the APUS 15:03 read whole', () => {
    expect(read.symbol).toBe('APUS');
    expect(read.plan?.entry).toBe(5.44);
    expect(read.plan?.checks.map(c => c.id)).toContain('vwap');
    expect(read.setups.find(l => l.setup_type === 'bull_flag')?.forming?.waiting).toBe('1 more red or doji candle');
    expect(read.groups.map(g => g.id)).toEqual(['in_play', 'setups', 'front', 'tape', 'short', 'float', 'halts']);
    expect(read.levels.hod).toEqual({ price: 8.74, ts: apusAt(9, 32) });
  });

  it('drops what it cannot read and refuses what is not a read', () => {
    const junk = {
      ...apusReadWire,
      groups: [...apusReadWire.groups, { id: 'weather', rows: [] }, null],
      setups: [...apusReadWire.setups, { state: 'leg' }],
      plan: { ...apusReadWire.plan, state: 'dancing', checks: [{ id: 'x' }], marks: [{ price: 'high' }] },
    };
    const out = normalizeStockRead(junk);
    expect(out?.groups).toHaveLength(7);
    expect(out?.setups).toHaveLength(4);
    expect(out?.plan?.state).toBe('forming');
    expect(out?.plan?.checks).toEqual([]);
    expect(out?.plan?.marks).toEqual([]);
    expect(normalizeStockRead({ symbol: 'APUS' })).toBeNull();
    expect(normalizeStockRead(null)).toBeNull();
  });

  it('reads a row state it does not know as unknown, never as a verdict', () => {
    const odd = { ...apusReadWire, groups: [{ ...apusReadWire.groups[0], verdict: 'great', rows: [
      { id: 'a', label: 'A', value: '1', state: 'amazing', source: 'x' },
    ] }] };
    const out = normalizeStockRead(odd);
    expect(out?.groups[0].verdict).toBe('unknown');
    expect(out?.groups[0].rows[0].state).toBe('unknown');
  });

  it('reads the decisions and the history, the split as the backend states it', () => {
    const d = normalizeDecisions(apusDecisionsWire);
    expect(d?.events).toHaveLength(4);
    expect(d?.events[1].levels?.leg?.high).toBe(7.23);
    expect(d?.sources.borrow).toEqual({ ok: false, error: 'OSError: locked' });
    expect(d?.summary.refusals[0].count).toBe(3);
    const h = normalizeHistory(apusHistoryWire);
    expect(h?.daily).toHaveLength(6);
    expect(h?.split).toEqual({ factor: '1:10', ts: expect.any(Number), reverse: true, days_ago: 63.2 });
    expect(normalizeHistory({ runs: [] })).toBeNull();
  });
});

describe('the plan box', () => {
  const plan = read.plan!;
  const lane = planLane(plan, read.setups);

  it('sizes a trade from the operator risk, in whole shares', () => {
    expect(sizeFor(20, 0.11)).toBe(181);
    expect(sizeFor(20, 0.2)).toBe(100);
    expect(sizeFor(5, 10)).toBeNull();
    expect(sizeFor(20, null)).toBeNull();
    expect(sizeFor(20, 0)).toBeNull();
  });

  it('says where a forming setup stands', () => {
    expect(formingProgress(lane)).toBe('1/2');
    expect(planBadge(plan, lane)).toBe('FORMING 1/2');
    expect(planFootnote(plan, lane)).toBe('provisional: arms after 1 more red or doji candle');
    expect(planBadgeText(read)).toBe('BULL FLAG · FORMING 1 OF 2');
    expect(planBadgeShort(plan, lane)).toBe('FLAG 1/2');
    expect(planBadgeShort({ ...plan, source: 'manual' }, null)).toBe('YOUR PLAN');
    expect(tileValue(read.groups.find(g => g.id === 'setups')!, read)).toBe('Flag 1/2');
    expect(tileValue(read.groups.find(g => g.id === 'front')!, read)).toBe('Mixed');
  });

  it('writes the rule under each number', () => {
    const sub = planSubLines(plan, 20, 181);
    expect(sub.entry).toBe('5.43 + 0.01');
    expect(sub.stop).toBe("flag's low");
    // Each target says the words it came from (#845), never a multiple of the risk.
    expect(sub.target).toBe('1c under $5.50');
    expect(sub.target2).toBe('1c under $6.00');
    expect(sub.risk).toBe('≤ 0.20 cap ✓');
    expect(stopCap(plan)).toBe(0.2);
  });

  it("names the menu's two targets with their shares, and says when everything sells at target 1 (#845)", () => {
    const words = planTargetWords(plan);
    expect(words.first).toMatchObject({ key: 'Target 1 · 50%', why: '1c under $5.50' });
    expect(words.first.tip).toMatch(/^Target 1 5\.49 · 1c under \$5\.50: 50% sells here\. It is \+0\.5R from the entry \(R is the risk a share/);
    expect(words.second).toMatchObject({ key: 'Target 2 · 50%', why: '1c under $6.00' });
    expect(words.second.tip).toMatch(/^Target 2 5\.99 · 1c under \$6\.00: the rest sells here\./);
    const one = planTargetWords({ ...plan, target2: null, target1_fraction: 1,
      targets: { ...plan.targets!, first: { kind: 'fixed', price: 5.64, why: '+20c' }, second: null } });
    expect(one.first).toMatchObject({ key: 'Target 1', why: '+20c' });
    expect(one.second).toMatchObject({ key: 'Target 2', why: 'everything at target 1' });
    // A plan from a backend before the menu: target 1 alone, its rule under it.
    const older = planTargetWords({ ...plan, target2: null, target1_fraction: 1, targets: null, target_rule: 'the pole high' });
    expect(older.first).toMatchObject({ key: 'Target 1', why: 'the pole high' });
    // The header's R: the targets' distance in the unit results are measured in.
    expect(rrText(plan.rr, plan.rr2 ?? null)).toBe('+0.5R · +5.0R');
    expect(rrText(1.25)).toBe('+1.3R');
    expect(rrText(null)).toBe('—');
  });

  it('drags a hand plan with each target keeping its distance from the entry, R following the new risk (#845)', () => {
    const hand = { ...plan, source: 'manual' as const };
    const d = draggedPlan(hand, { entry: 5.5, stop: 5.4 });
    expect(d).toMatchObject({ entry: 5.5, stop: 5.4 });
    expect(d.target).toBeCloseTo(5.55, 6);       // 5c over the entry, as before the drag
    expect(d.target2).toBeCloseTo(6.05, 6);      // 55c over it
    expect(d.risk).toBeCloseTo(0.1, 6);
    expect(d.rr).toBeCloseTo(0.5, 6);
    expect(d.rr2).toBeCloseTo(5.5, 6);
    // One target: target 2 stays none.
    const one = draggedPlan({ ...hand, target2: null }, { entry: 5.5, stop: 5.4 });
    expect(one.target2).toBeNull();
    expect(one.rr2).toBeNull();
  });

  it('lays the ruler out from the stop to target 2, target 1 ticked between, the price and what stands between', () => {
    const lay = rulerLayout(plan, 5.37)!;
    expect(lay.stopPct).toBeLessThan(lay.entryPct);
    expect(lay.entryPct).toBeLessThan(lay.target1Pct!);
    expect(lay.target1Pct!).toBeLessThan(lay.targetPct);
    expect(lay.marks.map(m => m.label)).toEqual(['T1', 'T2', '5.50']);
    expect(lay.marks.find(m => m.label === '5.50')!.pct).toBeGreaterThan(lay.entryPct);
    expect(lay.now?.edge).toBeNull();
    expect(rulerLayout(plan, 9)!.now?.edge).toBe('high');
    expect(rulerLayout({ ...plan, stop: null }, 5.37)).toBeNull();
    // One target: target 1 is the end, nothing ticked between.
    const one = rulerLayout({ ...plan, target2: null }, 5.37)!;
    expect(one.target1Pct).toBeNull();
    expect(one.marks.map(m => m.label)).toEqual(['5.50']);
  });

  it('leaves off a ruler label that would touch a stronger one, and keeps its tick', () => {
    // ACN's 27 marks printed their prices on top of each other (operator report 2026-10-01).
    const marks = [
      { pct: 40, label: '225.00', kind: 'round' },
      { pct: 41, label: 'HOD 226.50', kind: 'level' },
      { pct: 60, label: '230.00', kind: 'round' },
      { pct: 61, label: '230.10', kind: 'round' },
    ];
    const placed = placeRulerLabels(marks, 600, 30);
    expect(placed.map(m => [m.label, m.showLabel])).toEqual([
      ['225.00', false], ['HOD 226.50', true], ['230.00', true], ['230.10', false],
    ]);
    // A wide ruler has room for all of them.
    expect(placeRulerLabels(marks, 6000, 30).every(m => m.showLabel)).toBe(true);
    expect(rulerLayout({ ...plan, target2: null }, 5.37, 900)!.marks.every(m => m.showLabel)).toBe(true);
    // T1 sits 1c under $5.50: the target keeps its label, the round keeps its tick.
    expect(rulerLayout(plan, 5.37, 900)!.marks.map(m => [m.label, m.showLabel]))
      .toEqual([['T1', true], ['T2', true], ['5.50', false]]);
  });

  it('prints prices the way the desk does, and takes a sane risk per trade', () => {
    expect(fmtPx(5.4)).toBe('5.40');
    expect(fmtPx(0.1234)).toBe('0.1234');
    expect(fmtPx(null)).toBe('—');
    expect(fmtStep(0.01, 5.44)).toBe('0.01');
    expect(fmtStep(0.0012, 0.51)).toBe('0.0012');
    expect(parseRiskUsd('$25')).toBe(25);
    expect(parseRiskUsd('0')).toBeNull();
    expect(parseRiskUsd('abc')).toBeNull();
    expect(parseRiskUsd(50_000)).toBeNull();
  });
});

describe('the charts', () => {
  it('picks what each pane draws', () => {
    expect(paneKind('1Min')).toBe('full');
    expect(paneKind('5Min')).toBe('map');
    expect(paneKind('10Sec')).toBe('thin');
    expect(paneKind('1Day')).toBe('daily');
    expect(paneKind('15Min')).toBe('none');
  });

  it('draws the forming flag, its pole, its strategy box and the levels on the 1-minute pane', () => {
    const { scene, lines } = paneDraw(read, { pane: 'full', layers: LAYERS, toTime: identity });
    const labels = scene.boxes.map(b => b.label);
    expect(labels).toContain('POLE +7.1%');
    expect(labels).toContain('FLAG 1/2');
    const pole = scene.boxes.find(b => b.label === 'POLE +7.1%')!;
    expect(pole.t1).toBe(apusAt(14, 59)); // 3 pole candles ending 15:01
    expect(pole.t2).toBe(apusAt(15, 1));
    // Only forming (2026-10-12): its strategy box, never zones or plan lines across the pane.
    expect(scene.boxes.filter(b => b.t2 === null)).toEqual([]);
    expect(scene.strategy).toMatchObject({ entry: 5.44, stop: 5.33, target: 5.49, target2: 5.99, side: 'long',
      name: 'BULL FLAG', word: 'strategy', startBars: null, endBars: null, when: '' });  // its window closed at 11:30
    // Its prices are the edge column's words, faint, with no line of their own; target 2's too (2026-10-13).
    expect((scene.words ?? []).filter(w => w.id.startsWith('strategy:')).map(w => [w.text, w.style]))
      .toEqual([['T2 5.99', 'plain'], ['T1 5.49', 'plain'], ['entry 5.44', 'plain'], ['stop 5.33', 'plain']]);
    // The box stays in view, stop to target 1; target 2 never stretches the pane.
    expect(scene.keepInView).toEqual({ min: 5.33, max: 5.49 });
    expect(lines.filter(l => ['entry', 'stop', 'target', 'target2'].includes(l.id))).toEqual([]);
    expect(scene.edgeTags.map(t => t.label)).toEqual(expect.arrayContaining(['VWAP 6.09']));
    // The premarket high is the 5-minute pane's (the day's structure), never a 1-minute line or tag.
    expect(scene.edgeTags.some(t => t.label.startsWith('PMH'))).toBe(false);
  });

  it('draws an armed plan as its box in full colour: its prices on the axis, no line across the pane', () => {
    // Operator ask 2026-10-12, on an armed plan's zones and full-width lines: "its making the chart extremely big".
    const armed: StockRead = { ...read, plan: { ...read.plan!, state: 'armed', provisional: false } };
    const { scene, lines } = paneDraw(armed, { pane: 'full', layers: LAYERS, toTime: identity });
    expect(scene.boxes.filter(b => b.t2 === null)).toEqual([]);
    expect(scene.strategy).toMatchObject({ entry: 5.44, stop: 5.33, target: 5.49, target2: 5.99, side: 'long',
      state: 'armed', name: 'BULL FLAG', word: 'armed', startBars: null, endBars: null });
    // Each level keeps its axis tag, dashed while only a plan (ADR 037), with no line and no title: the box and the
    // column's words name them.
    const byId = Object.fromEntries(lines.map(l => [l.id, l]));
    expect(Object.keys(byId).sort()).toEqual(['entry', 'stop', 'target', 'target2']);
    for (const l of Object.values(byId)) {
      expect(l).toMatchObject({ line: false, title: '', axisLabel: true, style: 'dashed' });
    }
    expect(byId.entry.price).toBe(5.44);
    expect((scene.words ?? []).filter(w => w.id.startsWith('strategy:')).map(w => [w.text, w.price]))
      .toEqual([['T2', 5.99], ['T1', 5.49], ['entry', 5.44], ['stop', 5.33]]);
    // The box stays in view, stop to target 1; target 2 at 5.99 never stretches the pane.
    expect(scene.keepInView).toEqual({ min: 5.33, max: 5.49 });
  });

  it("keeps an armed plan's zones and lines, framed to target 2, where an order stands behind a level", () => {
    const armed: StockRead = { ...read, plan: { ...read.plan!, state: 'armed', provisional: false } };
    const levels = {
      entry: { price: 5.44, behind: 'order' as const }, stop: { price: 5.33, behind: 'plan' as const },
      target: { price: 5.49, behind: 'plan' as const }, target2: { price: 5.99, behind: 'plan' as const },
    };
    const { scene, lines } = paneDraw(armed, { pane: 'full', layers: LAYERS, toTime: identity, levels });
    expect(scene.strategy ?? null).toBeNull();
    expect(scene.boxes.filter(b => b.t2 === null).map(z => [z.p1, z.p2])).toEqual([[5.33, 5.44], [5.44, 5.49]]);
    // The pane frames the stop to the furthest target (#845): target 2 at 5.99 is a line on the chart.
    expect(scene.keepInView).toEqual({ min: 5.33, max: 5.99 });
    const byId = Object.fromEntries(lines.map(l => [l.id, l]));
    expect(byId.entry).toMatchObject({ price: 5.44, style: 'solid', title: 'ENTRY · working', axisLabel: true });
    expect(byId.entry.line).toBeUndefined();
    // Only a plan behind the stop and the targets: dashed, and they say so (ADR 037).
    expect(byId.target).toMatchObject({ title: 'TARGET 1 · plan', style: 'dashed' });
    expect(byId.target2).toMatchObject({ price: 5.99, title: 'TARGET 2 · plan', style: 'dashed', width: 1 });
    expect(byId.stop).toMatchObject({ title: 'STOP · plan', style: 'dashed' });
    // The day's levels come from the read's level map (none in this read): no bare lines in their place.
    expect(Object.keys(byId).sort()).toEqual(['entry', 'stop', 'target', 'target2']);
  });

  it('mirrors only thin lines on the 5-minute and 10-second panes', () => {
    const { scene, lines } = paneDraw(read, { pane: 'thin', layers: LAYERS, toTime: identity });
    expect(scene.boxes).toEqual([]);
    expect(lines.filter(l => ['entry', 'stop', 'target', 'target2'].includes(l.id)).every(l => l.width === 1 && l.title === '')).toBe(true);
    expect(lines.map(l => l.id)).toEqual(['entry', 'stop', 'target', 'target2']);
  });

  it('honours the switches: a hidden lane, setups off, levels off', () => {
    const hidden = paneDraw(read, { pane: 'full', layers: { ...LAYERS, hidden: ['bull_flag'] }, toTime: identity });
    expect(hidden.scene.boxes).toEqual([]);
    const off = paneDraw(read, { pane: 'full', layers: { ...LAYERS, setups: false }, toTime: identity });
    expect(off.lines).toEqual([]);
    const bare = paneDraw(read, { pane: 'full', layers: { ...LAYERS, levels: false }, toTime: identity });
    expect(bare.scene.edgeTags).toEqual([]);
  });

  it('keeps a failed setup on the chart, faded and named with the rule it broke', () => {
    const failed = normalizeStockRead({
      ...apusReadWire,
      plan: null,
      setups: [{
        ...apusReadWire.setups[0], state: 'failed', reason: 'the pullback ran past 3 candles',
        leg: { t: apusAt(9, 24), high: 7.23, low: 5.76, pct: 0.256 },
        setup: { trigger: 7.02, entry: 7.03, stop: 6.74, risk: 0.29, target1: 7.61, leg_t: apusAt(9, 24),
          pullback_bars: 2, armed_bar_t: apusAt(9, 26) },
      }],
    })!;
    const { scene } = paneDraw(failed, { pane: 'full', layers: LAYERS, toTime: identity });
    const pb = scene.boxes.find(b => b.label?.startsWith('PULLBACK'))!;
    expect(pb.label).toBe('PULLBACK 2 · FAILED: ran too long');
    expect(pb.stroke).toBe('#8e8e93');
    expect(scene.boxes.find(b => b.label === 'LEG +25.6%')?.stroke).toBe('#8e8e93');
  });

  it('draws nothing it cannot place on the pane', () => {
    const { scene } = paneDraw(read, { pane: 'full', layers: LAYERS, toTime: () => null });
    expect(scene.boxes).toEqual([]);
    expect(paneDraw(null, { pane: 'full', layers: LAYERS, toTime: identity }).lines).toEqual([]);
  });

  it('marks a decision the operator asked to see, with the levels it armed at', () => {
    const { scene } = paneDraw(read, {
      pane: 'full', layers: LAYERS, toTime: identity,
      focus: { ts: apusAt(9, 26), title: 'Armed', setup: { trigger: 7.0, stop: 6.7, target1: 7.6, armed_bar_t: apusAt(9, 25) } },
    });
    expect(scene.vlines).toEqual([{ t: apusAt(9, 26), color: '#ffd60a', label: 'Armed' }]);
    expect(scene.segments.filter(s => s.t1 === apusAt(9, 25)).map(s => s.price)).toEqual([7.0, 6.7, 7.6]);
  });

  it('names each lane on the legend in its own words', () => {
    const chips = read.setups.map(laneChip);
    // Past its window a lane can no longer arm today; a forming one still says how far it got.
    expect(chips.map(c => c.text)).toEqual(['1st pullback closed', 'Bull flag 1/2', 'Flat top closed', 'Red→green closed']);
    expect(chips[1].state).toBe('forming');
  });
});

describe('the sheet', () => {
  it('summarizes the read in one line', () => {
    const text = readSummary(read);
    expect(text).toMatch(/^APUS at 15:03 ET: In play Yes · Setups Flag forming · Front Mixed/);
    expect(text).toContain('entry 5.44, stop 5.33, target 1 5.49 (+0.5R), target 2 5.99 (+5.0R)');
  });

  it('summarizes the history without inventing a close', () => {
    const text = historySummary(normalizeHistory(apusHistoryWire)!);
    expect(text).toContain('ran +40% or more on 1 day');
    expect(text).toContain('Today so far: high +282%');
    expect(text).toContain('A 1-for-10 reverse split 63 days ago.');
  });

  it('colours each decision for a long trade', () => {
    const d = normalizeDecisions(apusDecisionsWire)!;
    expect(d.events.map(eventTone)).toEqual(['ok', 'info', 'bad', 'info']);
  });
});
