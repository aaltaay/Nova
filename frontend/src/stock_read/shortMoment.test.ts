/**
 * A short on the Trader, pure (ADR 048, #778 step 3): the moment while you hold one (the badge, COVER NOW, BROKE ·
 * NEXT with the lower offered), the held query and the stop resting at the broker, and a short plan's numbers, ruler,
 * drag and chart lines. RDYN short 416 at 5.77, the price 5.46, the buy stop 5.89.
 */
import { describe, expect, it } from 'vitest';
import { heldRuler } from './heldView';
import { normalizeHeld } from './heldRead';
import { RDYN_SHORT_NOW, RDYN_SHORT_SINCE, rdynShortWire } from './heldFixtures';
import { heldQty, NO_HELD, type MomentInputs } from './momentModel';
import { heldAnyQty, momentOfSides, nextHeldSides, shortQty } from './momentShort';
import { planActions } from './planActions';
import { planFootnote, planSubLines, rulerLayout } from './planMath';
import { inputs, pfsaPlan, pfsaRead } from './momentFixtures';
import { protectiveStop } from './protectiveStop';
import { levelTitle } from './tradeLevels';
import { draggedPlan } from './usePlanDrag';
import { heldQuery } from './useHeldTrade';
import { planQuery, readQuery } from './useStockRead';

const HELD = normalizeHeld(rdynShortWire)!;
const short = { position: { qty: -416, avgCost: 5.77 }, last: 5.46 };
const at = (over: Partial<MomentInputs> = {}, wire = rdynShortWire) => inputs({
  read: { ...pfsaRead('triggered'), symbol: 'RDYN', price: 5.46, plan: null, held: normalizeHeld(wire) },
  ...short, now: RDYN_SHORT_NOW, ...over,
}, { ...NO_HELD, since: RDYN_SHORT_SINCE });

const SHORT_PLAN = pfsaPlan('manual', {
  source: 'manual', side: 'short', setup_type: null, setup_id: null, kind: null, trigger: null,
  // The menu's covers under the entry (#845): 20c under it, then 1c over $5.50 for the rest.
  entry: 5.77, stop: 5.89, target: 5.57, target2: 5.51, target1_fraction: 0.5, risk: 0.12, reward: 0.2, rr: 1.67,
  reward2: 0.26, rr2: 2.17,
  targets: { first: { kind: 'fixed', price: 5.57, why: '-20c' }, second: { kind: 'next_level', price: 5.51, why: '1c over $5.50' },
    hod: null, pullback_high: null, stop: null, rule: null },
  target_rule: 'target 1: 20c, or 1c before a half / whole dollar when that is closer; target 2: 1c before the high of '
    + 'day, else 1c before the next level past target 1; 50% at target 1',
  entry_rule: 'your entry', stop_rule: 'your buy stop', tape: null, grade: null, pillars: null, trade: null,
});

describe('the moment while you hold a short', () => {
  it('counts the shares short, and never as a long', () => {
    const i = at();
    expect(shortQty(i)).toBe(416);
    expect(heldQty(i)).toBe(0);
    expect(heldAnyQty(i)).toBe(416);
    // Flat is flat: no shares either way.
    const flat = at({ position: null });
    expect([heldQty(flat), shortQty(flat), heldAnyQty(flat)]).toEqual([0, 0, 0]);
  });

  it('BROKE $5.50 · NEXT 5.35 offers the lower, on the badge and as a call; the track reads Short, Your cover', () => {
    const m = momentOfSides(at());
    expect(m).toMatchObject({ side: 'short', step: 2, exitLabel: 'Your cover', tone: 'holding' });
    expect(m?.badge).toBe('SHORT 416 · BROKE $5.50 · NEXT 5.35');
    expect(m?.call).toMatchObject({ title: 'BROKE $5.50 · NEXT 5.35', tone: 'go', ping: true });
    expect(m?.call?.detail).toMatch(/Lower the stop to 5.55, 5c over \$5.50\?/);
  });

  it('reads the open P&L with no lower on offer', () => {
    const m = momentOfSides(at({}, { ...rdynShortWire, lower: null }));
    expect(m?.badge).toBe('SHORT 416 · +$128.96');
    expect(m?.call).toBeNull();
  });

  it('calls COVER NOW when the buy stop prints, or the cover target trades', () => {
    const first = at({}, { ...rdynShortWire, lower: null });
    const stopHit = nextHeldSides(nextHeldSides(first.held, first), { ...first, last: 5.9 });
    const m = momentOfSides({ ...first, last: 5.9, held: stopHit });
    expect(m?.badge).toBe('STOP ↑ 5.89 HIT · COVER');
    expect(m?.call).toMatchObject({ title: 'COVER NOW · STOP ↑ 5.89', tone: 'stop', ping: true });
    expect(m?.call?.detail).toMatch(/the cover is yours\. At the stop the short is about -\$49\.92\./);
    const targetHit = nextHeldSides(first.held, { ...first, last: 5.52 });
    expect(momentOfSides({ ...first, last: 5.52, held: targetHit })?.badge).toBe('TARGET ↓ 5.57 HIT · COVER');
  });

  it("offers no lower on Nova's own resting buy stop", () => {
    const nova = { ...rdynShortWire, stop: { ...(rdynShortWire.stop as object), source: 'nova' } };
    const m = momentOfSides(at({}, nova));
    expect(m?.badge).toBe('SHORT 416 · +$128.96');
    expect(m?.call).toBeNull();
  });
});

describe('the held query and the stop resting at the broker', () => {
  it('asks about a short as held_side=short with its shares counted positive', () => {
    expect(heldQuery({ qty: -416, avgCost: 5.77 }, { since: RDYN_SHORT_SINCE, stop: 5.89, risk: 0.12 }))
      .toBe('held_qty=416&held_avg=5.77&held_stop=5.89&held_risk=0.12&held_since=1791382500&held_side=short');
  });

  it('takes the resting stop when the tab has none of its own', () => {
    const track = { since: RDYN_SHORT_SINCE, stop: null, risk: null };
    expect(heldQuery({ qty: -416, avgCost: 5.77 }, track, 5.89)).toMatch(/held_stop=5.89/);
    expect(heldQuery({ qty: -416, avgCost: 5.77 }, { ...track, stop: 5.95 }, 5.89)).toMatch(/held_stop=5.95/);
  });

  it('finds the protective stop: the lowest buy stop over a short, the highest sell stop under a long', () => {
    const orders = [
      { symbol: 'RDYN', side: 'BUY' as const, order_type: 'STP', stop_price: 5.89 },
      { symbol: 'RDYN', side: 'BUY' as const, order_type: 'STP LMT', stop_price: 5.95 },
      { symbol: 'RDYN', side: 'BUY' as const, order_type: 'LMT', stop_price: null },
      { symbol: 'RDYN', side: 'BUY' as const, order_type: 'TRAIL', stop_price: 0.1 },
      { symbol: 'RDYN', side: 'SELL' as const, order_type: 'STP', stop_price: 5.2 },
      { symbol: 'OTHER', side: 'BUY' as const, order_type: 'STP', stop_price: 5.0 },
    ];
    expect(protectiveStop(orders, 'rdyn', -416)).toBe(5.89);
    expect(protectiveStop(orders, 'RDYN', 100)).toBe(5.2);
    expect(protectiveStop(orders, 'RDYN', 0)).toBeNull();
    expect(protectiveStop([], 'RDYN', -416)).toBeNull();
  });

  it('runs the held ruler downward: the buy stop at the left, the levels under the price at the right', () => {
    const lay = heldRuler(HELD, 600)!;
    expect(lay.stopPct!).toBeLessThan(lay.costPct);
    expect(lay.costPct).toBeLessThan(lay.nowPct!);
    expect(lay.nowPct!).toBeLessThan(lay.endPct);
    expect(lay.risk).toEqual([lay.stopPct, lay.costPct]);        // the stop is over your average: your risk
    expect(lay.marks.map(m => m.kind).sort()).toEqual(['broke', 'next', 'target', 'target']);
    expect(lay.marks.filter(m => m.kind === 'target').map(m => m.label)).toEqual(['T1', 'T2']);
  });
});

describe('a short plan', () => {
  it('reads Short at / Buy stop / Cover 1 / Cover 2 in its words, and its ruler runs from the buy stop down', () => {
    expect(planSubLines(SHORT_PLAN, 20, 166)).toMatchObject({ entry: 'your short', target: '-20c', target2: '1c over $5.50' });
    expect(planFootnote(SHORT_PLAN, null)).toBe('drag the short or its buy stop on the 1-minute chart; the covers follow the entry');
    const lay = rulerLayout(SHORT_PLAN, 5.75)!;
    expect(lay.stopPct).toBeLessThan(lay.entryPct);
    // Cover 1 between the entry and cover 2, the right end.
    expect(lay.entryPct).toBeLessThan(lay.target1Pct!);
    expect(lay.target1Pct!).toBeLessThan(lay.targetPct);
    expect(lay.now).toMatchObject({ edge: null });
    expect(rulerLayout(SHORT_PLAN, 6.5)?.now?.edge).toBe('low');       // over the buy stop
    expect(rulerLayout(SHORT_PLAN, 5.0)?.now?.edge).toBe('high');      // under cover 2
  });

  it('drags its entry under the buy stop, each cover keeping its distance under it', () => {
    const d = draggedPlan(SHORT_PLAN, { entry: 5.7, stop: 5.9 });
    expect(d).toMatchObject({ entry: 5.7, stop: 5.9 });
    expect(d.target).toBeCloseTo(5.5, 6);
    expect(d.target2).toBeCloseTo(5.44, 6);
    expect(d.rr).toBeCloseTo(1, 6);                // 20c on the new 20c risk: R follows the risk, the cover does not
    expect(d.rr2).toBeCloseTo(1.3, 6);
  });

  it('asks the read for a hand short with side=short', () => {
    expect(planQuery(5.77, 5.89, 'short')).toBe('?entry=5.77&stop=5.89&side=short');
    expect(readQuery(5.77, null, 'held_qty=1&held_avg=2', 'short')).toBe('?entry=5.77&side=short&held_qty=1&held_avg=2');
    expect(planQuery(5.77, null)).toBe('?entry=5.77');
  });

  it('names its chart lines SHORT, STOP ↑ and TARGET 1 ↓ / TARGET 2 ↓', () => {
    expect(levelTitle('entry', 'plan', true)).toBe('SHORT');
    expect(levelTitle('entry', 'held', true)).toBe('SHORT · held');
    expect(levelTitle('stop', 'plan', true)).toBe('STOP ↑ · plan');
    expect(levelTitle('target', 'plan', true)).toBe('TARGET 1 ↓ · plan');
    expect(levelTitle('target2', 'plan', true)).toBe('TARGET 2 ↓ · plan');
    expect(levelTitle('entry', 'plan')).toBe('ENTRY');
    expect(levelTitle('target', 'plan')).toBe('TARGET 1 · plan');
  });

  it('stages a short in the ticket with its buy stop', () => {
    const read = { ...pfsaRead('triggered'), plan: SHORT_PLAN };
    const actions = planActions({ moment: null, inputs: inputs({ read }), bid: 5.76,
      listening: true, stageLocked: null, symbol: 'RDYN' });
    expect(actions.map(a => a.label)).toEqual(['Stage short in ticket']);
    expect(actions[0].tip).toMatch(/with the plan's buy stop/);
  });
});
