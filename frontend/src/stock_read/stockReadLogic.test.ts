import type { Time } from 'lightweight-charts';
import { describe, expect, it } from 'vitest';
import { laneChip, paneDraw, paneKind, planBadgeText } from './chartShapes';
import { normalizeDecisions, normalizeHistory, normalizeStockRead } from './normalize';
import {
  fmtPx,
  fmtStep,
  formingProgress,
  planBadgeShort,
  parseRiskUsd,
  planBadge,
  planFootnote,
  planLane,
  planSubLines,
  rulerLayout,
  sizeFor,
  stopCap,
} from './planMath';
import { historySummary } from './HistoryTab';
import { tileValue } from './ReadStrip';
import { readSummary } from './SignalsTab';
import { eventTone } from './DecisionsTab';
import { apusAt, apusDecisionsWire, apusHistoryWire, apusReadWire } from './stockReadFixtures';
import type { StockRead } from './types';

const LAYERS = { setups: true, levels: true, hidden: [] as string[], plan: 'auto' as const };
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
    expect(sub.target).toBe('entry + 2 × 0.11');
    expect(sub.risk).toBe('≤ 0.20 cap ✓');
    expect(stopCap(plan)).toBe(0.2);
  });

  it('lays the ruler out from the stop to the target, the price and what stands between', () => {
    const lay = rulerLayout(plan, 5.37)!;
    expect(lay.stopPct).toBeLessThan(lay.entryPct);
    expect(lay.entryPct).toBeLessThan(lay.targetPct);
    expect(lay.marks).toHaveLength(1);
    expect(lay.marks[0].pct).toBeGreaterThan(lay.entryPct);
    expect(lay.now?.edge).toBeNull();
    expect(rulerLayout(plan, 9)!.now?.edge).toBe('high');
    expect(rulerLayout({ ...plan, stop: null }, 5.37)).toBeNull();
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
    expect(paneKind('5Min')).toBe('thin');
    expect(paneKind('10Sec')).toBe('thin');
    expect(paneKind('1Day')).toBe('none');
  });

  it('draws the forming flag, its pole, the plan and the levels on the 1-minute pane', () => {
    const { scene, lines } = paneDraw(read, { pane: 'full', layers: LAYERS, toTime: identity });
    const labels = scene.boxes.map(b => b.label);
    expect(labels).toContain('POLE +7.1%');
    expect(labels).toContain('FLAG 1/2');
    const pole = scene.boxes.find(b => b.label === 'POLE +7.1%')!;
    expect(pole.t1).toBe(apusAt(14, 59)); // 3 pole candles ending 15:01
    expect(pole.t2).toBe(apusAt(15, 1));
    const zones = scene.boxes.filter(b => b.t2 === null);
    expect(zones.map(z => [z.p1, z.p2])).toEqual([[5.33, 5.44], [5.44, 5.66]]);
    expect(scene.keepInView).toEqual({ min: 5.33, max: 5.66 });
    const byId = Object.fromEntries(lines.map(l => [l.id, l]));
    expect(byId.entry).toMatchObject({ price: 5.44, style: 'dashed', title: 'ENTRY (provisional)', axisLabel: true });
    expect(byId.target.title).toBe('TARGET 2R');
    expect(byId.hod.price).toBe(8.74);
    expect(byId.round_above.title).toBe('$5.50');
    expect(scene.edgeTags.map(t => t.label)).toEqual(
      expect.arrayContaining(['HOD 8.74', 'PMH 7.31', 'VWAP 6.09']),
    );
  });

  it('mirrors only thin lines on the 5-minute and 10-second panes', () => {
    const { scene, lines } = paneDraw(read, { pane: 'thin', layers: LAYERS, toTime: identity });
    expect(scene.boxes).toEqual([]);
    expect(lines.filter(l => ['entry', 'stop', 'target'].includes(l.id)).every(l => l.width === 1 && l.title === '')).toBe(true);
    expect(lines.map(l => l.id)).toEqual(['entry', 'stop', 'target', 'hod']);
  });

  it('honours the switches: a hidden lane, setups off, levels off', () => {
    const hidden = paneDraw(read, { pane: 'full', layers: { ...LAYERS, hidden: ['bull_flag'] }, toTime: identity });
    expect(hidden.scene.boxes).toEqual([]);
    const off = paneDraw(read, { pane: 'full', layers: { ...LAYERS, setups: false }, toTime: identity });
    expect(off.lines.map(l => l.id)).toEqual(['hod', 'pmh', 'open', 'round_above', 'round_below']);
    const bare = paneDraw(read, { pane: 'full', layers: { ...LAYERS, levels: false }, toTime: identity });
    expect(bare.scene.edgeTags).toEqual([]);
  });

  it('keeps a failed setup on the chart, faded and named', () => {
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
    expect(pb.label).toBe('PULLBACK 2 · FAILED');
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
    expect(text).toContain('entry 5.44, stop 5.33, target 5.66, 2.0 : 1');
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
