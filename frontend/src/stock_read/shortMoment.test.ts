/**
 * A short on the Trader, pure (ADR 048, #778 step 3): the moment while you hold one (the badge, COVER NOW, BROKE ·
 * NEXT with the lower offered, the bot holding the cover), the held query and the stop resting at the broker, and
 * a short plan's numbers, ruler, drag and chart lines. RDYN short 416 at 5.77, the price 5.46, the buy stop 5.89.
 */
import { describe, expect, it } from 'vitest';
import { heldRuler } from './heldView';
import { normalizeHeld } from './heldRead';
import { RDYN_SHORT_NOW, RDYN_SHORT_SINCE, rdynShortWire } from './heldFixtures';
import { heldQty, NO_HELD, type MomentInputs } from './momentModel';
import { heldAnyQty, momentOfSides, nextHeldSides, shortQty } from './momentShort';
import { planActions } from './planActions';
import { planFootnote, planSubLines, rulerLayout } from './planMath';
import { protectiveStop } from './protectiveStop';
import type { StockModeTrade } from './types';
import { draggedPlan } from './usePlanDrag';
import { heldQuery } from './useHeldTrade';
import { planQuery, readQuery } from './useStockRead';
import { inputs, pfsaPlan, pfsaRead, pfsaView } from './whoTradesFixtures';
import { SHORT_APPROVE_LATER } from './planActions';
import { levelTitle } from './whoTradesModel';

const HELD = normalizeHeld(rdynShortWire)!;
const short = { position: { qty: -416, avgCost: 5.77 }, last: 5.46 };
const at = (over: Partial<MomentInputs> = {}, wire = rdynShortWire) => inputs({
  read: { ...pfsaRead('triggered'), symbol: 'RDYN', price: 5.46, plan: null, held: normalizeHeld(wire) },
  who: pfsaView('signal'), ...short, now: RDYN_SHORT_NOW, ...over,
}, { ...NO_HELD, since: RDYN_SHORT_SINCE });

const SHORT_PLAN = pfsaPlan('manual', {
  source: 'manual', side: 'short', setup_type: null, setup_id: null, kind: null, trigger: null,
  entry: 5.77, stop: 5.89, target: 5.53, risk: 0.12, reward: 0.24, rr: 2, target_rule: 'entry - 2 x risk',
  entry_rule: 'your entry', stop_rule: 'your buy stop', tape: null, grade: null, pillars: null, trade: null,
});

describe('the moment while you hold a short', () => {
  it('counts the shares short, and never as a long', () => {
    const i = at();
    expect(shortQty(i)).toBe(416);
    expect(heldQty(i)).toBe(0);
    expect(heldAnyQty(i)).toBe(416);
    // Nova's short trade is a short, not a long the positions read has not caught up with.
    const trade = { kind: 'exit', side: 'short', state: 'holding', qty: 416, exits: 'nova' } as unknown as StockModeTrade;
    const nova = at({ position: null, who: pfsaView('signal', { trade }) });
    expect(heldQty(nova)).toBe(0);
    expect(shortQty(nova)).toBe(416);
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
    expect(momentOfSides({ ...first, last: 5.52, held: targetHit })?.badge).toBe('TARGET ↓ 5.53 HIT · COVER');
  });

  it('says the bot holds the cover while it does', () => {
    const trade = { kind: 'exit', side: 'short', state: 'holding', exits: 'nova', stop: 5.55, target: null,
      fill_price: 5.77, entry: 5.77, qty: 416, trail: true, raised: [] } as unknown as StockModeTrade;
    const m = momentOfSides(at({ who: pfsaView('signal', { trade }) }));
    expect(m).toMatchObject({ exitLabel: 'Target / stop', side: 'short' });
    expect(m?.badge).toBe('BOT HOLDS THE COVER · +$128.96');
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
    expect(lay.marks.map(m => m.kind).sort()).toEqual(['broke', 'next', 'target']);
  });
});

describe('a short plan', () => {
  it('reads Short at / Buy stop / Cover in its words, and its ruler runs from the buy stop down', () => {
    expect(planSubLines(SHORT_PLAN, 20, 166)).toMatchObject({ entry: 'your short', target: 'entry - 2 × 0.12' });
    expect(planFootnote(SHORT_PLAN, null)).toBe('drag the short or its buy stop on the 1-minute chart; the cover stays 2R');
    const lay = rulerLayout(SHORT_PLAN, 5.75)!;
    expect(lay.stopPct).toBeLessThan(lay.entryPct);
    expect(lay.entryPct).toBeLessThan(lay.targetPct);
    expect(lay.now).toMatchObject({ edge: null });
    expect(rulerLayout(SHORT_PLAN, 6.5)?.now?.edge).toBe('low');       // over the buy stop
    expect(rulerLayout(SHORT_PLAN, 5.0)?.now?.edge).toBe('high');      // under the cover target
  });

  it('drags its entry under the buy stop, the cover following at 2R under it', () => {
    expect(draggedPlan(SHORT_PLAN, { entry: 5.7, stop: 5.9 })).toMatchObject({ entry: 5.7, stop: 5.9, target: 5.3, rr: 2 });
  });

  it('asks the read for a hand short with side=short', () => {
    expect(planQuery(5.77, 5.89, 'short')).toBe('?entry=5.77&stop=5.89&side=short');
    expect(readQuery(5.77, null, 'held_qty=1&held_avg=2', 'short')).toBe('?entry=5.77&side=short&held_qty=1&held_avg=2');
    expect(planQuery(5.77, null)).toBe('?entry=5.77');
  });

  it('names its chart lines SHORT, STOP ↑ and TARGET ↓', () => {
    expect(levelTitle('entry', 'plan', '', true)).toBe('SHORT');
    expect(levelTitle('stop', 'order', '', true)).toBe('STOP ↑ · order');
    expect(levelTitle('target', 'plan', ' 2R', true)).toBe('TARGET ↓ 2R · plan');
    expect(levelTitle('entry', 'plan')).toBe('ENTRY');
  });

  it('stages a short in the ticket, and waits on step 5 for Approve', () => {
    const read = { ...pfsaRead('triggered'), plan: SHORT_PLAN };
    const signal = planActions({ moment: null, inputs: inputs({ read, who: pfsaView('signal') }), bid: 5.76,
      listening: true, stageLocked: null, symbol: 'RDYN' });
    expect(signal.actions.map(a => a.label)).toEqual(['Stage short in ticket']);
    expect(signal.actions[0].tip).toMatch(/with the plan's buy stop/);
    const approve = planActions({ moment: null, inputs: inputs({ read, who: pfsaView('approve') }), bid: 5.76,
      listening: true, stageLocked: null, symbol: 'RDYN' });
    expect(approve.actions[0]).toMatchObject({ id: 'approve', locked: SHORT_APPROVE_LATER });
  });
});
