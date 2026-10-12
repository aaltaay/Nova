/**
 * Approve sells in two halves (#845, #681): the approval carries the plan's target 2 and its share, the APPROVED
 * card and Approve's hover say both limits, Level 2 marks target 2 as T2, and the 1-minute pane frames the stop to
 * the furthest target -- on PFSA's first pullback of 2026-09-24 with a target 2 at 4.80.
 */
import { describe, expect, it } from 'vitest';
import { paneDraw } from './chartShapes';
import { limitWords } from './exitTargets';
import { momentOf, type MomentInputs } from './momentModel';
import { approvedWords } from './momentWords';
import { planActions } from './planActions';
import { planFrame } from './planMath';
import type { StockModeApproval, StockPlan } from './types';
import { approveRequest } from './whoTradesApi';
import { inputs, PFSA_SETUP_ID, PFSA_TRIGGER, pfsaPlan, pfsaRead, pfsaTrade, pfsaView } from './whoTradesFixtures';
import { level2Markers, orderLevels } from './whoTradesModel';

const HALVES: Partial<StockPlan> = { target2: 4.80, target1_fraction: 0.5 };

function act(i: MomentInputs) {
  return planActions({ moment: momentOf(i), inputs: i, bid: 4.50, listening: true, stageLocked: null, symbol: 'PFSA' });
}

function approval(over: Partial<StockModeApproval> = {}): StockModeApproval {
  return { setup_id: PFSA_SETUP_ID, setup_type: 'first_pullback', entry: 4.27, stop: 4.14, target: 4.52, target2: 4.80,
    target1_fraction: 0.5, qty: 153, approved_at: PFSA_TRIGGER - 5, state: 'waiting', reason: null, ...over };
}

describe('the approval request', () => {
  it("carries the plan's target 2 and the share sold at target 1", () => {
    expect(approveRequest(pfsaPlan('armed', HALVES), 153, false)).toEqual({
      setup_id: PFSA_SETUP_ID, entry: 4.27, stop: 4.14, target: 4.52, target2: 4.80, target1_fraction: 0.5, qty: 153,
      now: false,
    });
  });

  it('sends no target 2 and no share for a plan that sells every share at target 1', () => {
    const body = approveRequest(pfsaPlan('triggered', { target2: null, target1_fraction: 1 }), 153, true);
    expect([body.target, body.target2, body.target1_fraction, body.now]).toEqual([4.52, null, null, true]);
  });
});

describe('what the approval says it sends', () => {
  it('names both limits, the first half the smaller part of an odd count', () => {
    expect(limitWords(153, 4.52, 4.80, 0.5, false)).toBe('LMT 4.52 x 76 and LMT 4.80 x 77');
    expect(limitWords(100, 6.12, 6.96, null, false)).toBe('LMT 6.12 x 50 and LMT 6.96 x 50');
    expect(limitWords(1, 6.12, 6.96, 0.5, false)).toBe('LMT 6.12 x 1');                  // one share: all at target 1
    expect(limitWords(100, 5.53, 5.30, 0.5, true)).toBe('LMT 5.53 x 50 and LMT 5.30 x 50');   // a short's covers
  });

  it('the APPROVED card says both halves; one target reads as before', () => {
    const plan = pfsaPlan('armed', HALVES);
    expect(approvedWords(plan, approval())).toBe(
      'Nova sends buy 153 @ 4.27 with stop 4.14, LMT 4.52 x 76 and LMT 4.80 x 77 when 4.26 prints with the tape at go.');
    expect(approvedWords(plan, approval({ target2: null }))).toBe(
      'Nova sends buy 153 @ 4.27 with stop 4.14 and target 4.52 when 4.26 prints with the tape at go.');
    const short = pfsaPlan('armed', { side: 'short', ...HALVES });
    expect(approvedWords(short, approval({ entry: 4.25, stop: 4.38, target: 3.99, target2: 3.80, qty: 7 }))).toBe(
      'Nova sends short 7 @ 4.25 with buy stop 4.38, LMT 3.99 x 3 and LMT 3.80 x 4 when 4.26 prints with the tape at go.');
    const waiting = momentOf(inputs({ read: pfsaRead('armed', HALVES), who: pfsaView('approve', { approval: approval() }) }));
    expect(waiting?.call).toMatchObject({ title: 'APPROVED' });
    expect(waiting?.call?.detail).toContain('LMT 4.52 x 76 and LMT 4.80 x 77');
  });

  it("Approve's hover names both limits it will send", () => {
    const [armed] = act(inputs({ read: pfsaRead('armed', HALVES), who: pfsaView('approve') })).actions;
    expect(armed.id).toBe('approve');
    expect(armed.tip).toMatch(/with its stop 4\.14, LMT 4\.52 x 76 and LMT 4\.80 x 77\. Withdrawn if/);
    const [one] = act(inputs({ read: pfsaRead('armed'), who: pfsaView('approve') })).actions;
    expect(one.tip).toMatch(/with its stop 4\.14 and target 4\.52\./);
  });

  it('the BOUGHT call names both limits and says the stop never moves', () => {
    const bracket = pfsaTrade('approve', 'holding', { target2: 4.80, target2_order_id: 104, target1_qty: 76,
      target2_qty: 77 });
    const m = momentOf(inputs({ read: pfsaRead('armed', HALVES), who: pfsaView('approve', { trade: bracket }),
      last: 4.30 }));
    expect(m?.call?.title).toBe('BOUGHT 153 @ 4.27');
    expect(m?.call?.detail).toBe('The stop 4.14 and both targets are working at the broker: LMT 4.52 x 76 and LMT '
      + "4.80 x 77. A target's fill shrinks the stop to the shares left; the stop never moves.");
  });

  it('cancels the stop and both targets while both rest, and the one left after a half sold', () => {
    const bracket = pfsaTrade('approve', 'holding', { target2: 4.80, target2_order_id: 104 });
    const [both] = act(inputs({ who: pfsaView('approve', { trade: bracket }) })).actions;
    expect(both).toMatchObject({ id: 'take-over', label: 'Cancel stop and targets' });
    expect(both.tip).toMatch(/^Nova cancels the bracket's stop and targets at the broker/);
    const half = { ...bracket, halves: [{ leg: 'target1', qty: 76, price: 4.52 }] };
    const [rest] = act(inputs({ who: pfsaView('approve', { trade: half }) })).actions;
    expect(rest.label).toBe('Cancel stop and target');
  });
});

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

  it("is solid while Approve's second limit rests, and target 1 is only the plan's once its half sold", () => {
    const bracket = pfsaTrade('approve', 'holding', { target2: 4.80, target2_order_id: 104 });
    const lv = orderLevels(inputs({ read: pfsaRead('armed', HALVES), who: pfsaView('approve', { trade: bracket }) }));
    expect([lv?.target?.behind, lv?.target2?.behind]).toEqual(['order', 'order']);
    expect(level2Markers(lv).find(m => m.id === 'target2')).toMatchObject({ label: 'T2 4.80', working: true });
    const half = { ...bracket, halves: [{ leg: 'target1', qty: 76, price: 4.52 }] };
    const after = orderLevels(inputs({ who: pfsaView('approve', { trade: half }) }));
    expect([after?.target?.behind, after?.target2?.behind]).toEqual(['plan', 'order']);
    // A trade that sells every share at target 1 marks no T2, whatever the plan says.
    const one = orderLevels(inputs({ read: pfsaRead('armed', HALVES), who: pfsaView('approve', { trade: pfsaTrade('approve', 'holding') }) }));
    expect(one?.target2).toBeNull();
  });
});

describe('the 1-minute pane frames both targets', () => {
  const LAYERS = { setups: true, levels: false, hidden: [], plan: 'auto' } as const;

  it('frames the stop to the furthest target, the mirror for a short', () => {
    expect(planFrame(4.14, 4.52, 4.80)).toEqual({ min: 4.14, max: 4.80 });
    expect(planFrame(4.14, 4.52, null)).toEqual({ min: 4.14, max: 4.52 });
    expect(planFrame(4.38, 3.99, 3.80)).toEqual({ min: 3.80, max: 4.38 });
    expect(planFrame(null, 4.52, 4.80)).toBeNull();
  });

  it('keeps target 2 in view, so it is a line on the chart with its own title', () => {
    const read = pfsaRead('armed', HALVES);
    const draw = paneDraw(read, { pane: 'full', layers: LAYERS, toTime: t => t as never });
    expect(draw.scene.keepInView).toEqual({ min: 4.14, max: 4.80 });
    const t2 = draw.lines.find(l => l.id === 'target2');
    expect(t2).toMatchObject({ price: 4.80, title: 'TARGET 2 · plan', axisLabel: true });
    const one = paneDraw(pfsaRead('armed'), { pane: 'full', layers: LAYERS, toTime: t => t as never });
    expect(one.scene.keepInView).toEqual({ min: 4.14, max: 4.52 });
  });

  it("draws Approve's second limit solid while it rests", () => {
    const bracket = pfsaTrade('approve', 'holding', { target2: 4.80, target2_order_id: 104 });
    const i = inputs({ read: pfsaRead('armed', HALVES), who: pfsaView('approve', { trade: bracket }), last: 4.30 });
    const draw = paneDraw(i.read, { pane: 'full', layers: LAYERS, toTime: t => t as never, levels: orderLevels(i) });
    expect(draw.lines.find(l => l.id === 'target2')).toMatchObject({ style: 'solid', title: 'TARGET 2 · order' });
    expect(draw.scene.keepInView).toEqual({ min: 4.14, max: 4.80 });
  });
});
