/**
 * The trade you hold (ADR 036 amendment 2026-10-01), pure: the wire, the ruler, the 10-second chart's
 * lines, Level 2's NEXT and STOP, the calls, and what the read is asked. On the operator's APUS Paper trade
 * of 2026-09-24 08:59:05 (holding 100 at 5.075, the price 6.64, $6.00 broke at the 08:58 close).
 */
import type { Time } from 'lightweight-charts';
import { describe, expect, it } from 'vitest';
import { paneDraw } from './chartShapes';
import { APUS_HELD_NOW, APUS_HELD_SINCE, apusHeldWire } from './heldFixtures';
import { normalizeHeld } from './heldRead';
import { heldLines, heldMarkers, heldRuler } from './heldView';
import { momentOf, NO_HELD } from './momentModel';
import type { StockReadLayers } from './StockReadContext';
import type { StockRead } from './types';
import { heldQuery, normalizeFlush } from './useHeldTrade';
import { readQuery } from './useStockRead';
import { inputs, pfsaRead, pfsaView } from './whoTradesFixtures';

const HELD = normalizeHeld(apusHeldWire)!;
const LAYERS: StockReadLayers = { setups: true, levels: false, past: false, labels: 'compact', hidden: [], plan: 'auto' };
const identity = (s: number) => s as unknown as Time;
const read = (over: Partial<StockRead> = {}): StockRead => ({ ...pfsaRead('triggered'), symbol: 'APUS', price: 6.64,
  plan: null, held: HELD, ...over });
const holding = { position: { qty: 100, avgCost: 5.075 }, last: 6.64 };

describe('the wire', () => {
  it('reads the held block, and nothing when nothing is held', () => {
    expect(HELD.stop).toEqual({ price: 5.45, source: 'yours', rule: 'your stop', printed: false });
    expect(HELD.raise?.to).toBe(5.95);
    expect(HELD.ladder.map(r => r.role)).toEqual(['then', 'next', 'now', 'through', 'broke', 'broke', 'stop', 'cost']);
    expect(HELD.levels.room?.text).toBe('0.7R to HOD 6.97, from the price');
    expect(normalizeHeld(null)).toBeNull();
    expect(normalizeHeld({ ...apusHeldWire, qty: 0 })).toBeNull();
    expect(normalizeHeld({ ...apusHeldWire, ladder: [{ role: 'invented', price: 1 }] })?.ladder).toEqual([]);
  });

  it('asks the read about the position, and nothing when flat', () => {
    expect(heldQuery({ qty: 100, avgCost: 5.075 }, { since: APUS_HELD_SINCE, stop: 5.45, risk: 0.445 }))
      .toBe('held_qty=100&held_avg=5.075&held_stop=5.45&held_risk=0.445&held_since=1790253888');
    expect(heldQuery(null, { since: null, stop: null, risk: null })).toBe('');
    expect(heldQuery({ qty: 100, avgCost: null }, { since: 1, stop: null, risk: null })).toBe('');
    expect(readQuery(5.39, null, 'held_qty=1&held_avg=2')).toBe('?entry=5.39&held_qty=1&held_avg=2');
    expect(readQuery(null, null, '')).toBe('');
    expect(normalizeFlush({ at: 1, score: -0.6, label: 'flush', window_sec: 30 })).toEqual({ at: 1, score: -0.6,
      label: 'flush', windowSec: 30 });
  });
});

describe('the ruler while you hold', () => {
  it('runs from your average past the stop to the level after next', () => {
    const lay = heldRuler(HELD, 600)!;
    expect(lay.costPct).toBeLessThan(lay.stopPct!);                 // the stop is over your average: locked in
    expect(lay.locked).toEqual([lay.costPct, lay.stopPct]);
    expect(lay.risk![0]).toBe(lay.stopPct);                          // red: what the stop gives back from here
    expect(lay.risk![1]).toBe(lay.nowPct);
    expect(lay.reward![0]).toBe(lay.nowPct);                         // green: to the next level, then dotted
    expect(lay.ahead).not.toBeNull();
    expect(lay.marks.map(m => m.kind).sort()).toEqual(['broke', 'broke', 'next', 'target', 'through']);
    expect(lay.marks.find(m => m.kind === 'next')!.showLabel).toBe(true);
  });

  it('draws the risk to the stop while the stop is under your average', () => {
    const under = normalizeHeld({ ...apusHeldWire, price: 5.2, stop: { price: 4.63, source: 'proposed', rule: 'x' } })!;
    const lay = heldRuler(under, 600)!;
    expect(lay.locked).toBeNull();
    expect(lay.risk).toEqual([lay.stopPct, lay.costPct]);
  });
});

describe('the charts and Level 2', () => {
  it('draws the ladder on the 10-second chart only, each line named', () => {
    const lines = heldLines(HELD);
    expect(lines.map(l => l.title)).toEqual(['THEN 7.50', 'NEXT 6.97', 'THROUGH 6.50', 'BROKE 6.00', 'BROKE 5.50',
      'STOP 5.45', 'COST 5.08']);
    expect(lines.every(l => l.axisLabel)).toBe(true);
    expect(paneDraw(read(), { pane: 'thin', layers: LAYERS, toTime: identity }).lines.map(l => l.title)).toContain('NEXT 6.97');
    const minute = paneDraw(read({ plan: pfsaRead('triggered').plan }), { pane: 'full', layers: LAYERS, toTime: identity });
    expect(minute.lines.filter(l => ['entry', 'stop', 'target'].includes(l.id))).toEqual([]);
    expect(minute.scene.boxes.filter(b => b.t2 === null)).toEqual([]);          // no plan zones while held
    const five = paneDraw(read({ plan: pfsaRead('triggered').plan }), { pane: 'map', layers: LAYERS, toTime: identity });
    expect(five.lines.filter(l => ['entry', 'stop', 'target'].includes(l.id))).toEqual([]);
  });

  it('marks NEXT with the asks and your STOP with the bids, solid once Nova holds it', () => {
    expect(heldMarkers(HELD).map(m => `${m.label}:${m.rests}:${m.working}`)).toEqual(['STOP 5.45:bid:false', 'NEXT 6.97:ask:false']);
    const nova = normalizeHeld({ ...apusHeldWire, stop: { price: 5.95, source: 'nova', rule: "Nova's resting stop" } })!;
    expect(heldMarkers(nova)[0]).toMatchObject({ label: 'STOP 5.95', working: true });
    expect(heldMarkers(null)).toEqual([]);
  });
});

describe('the calls while you hold', () => {
  const at = (over = {}, since = APUS_HELD_SINCE) => inputs({ read: read(), who: pfsaView('signal'), ...holding,
    now: APUS_HELD_NOW, ...over }, { ...NO_HELD, since });

  it('BROKE offers the raise, and names the next level', () => {
    const m = momentOf(at());
    expect(m?.badge).toBe('BROKE $6.00 · NEXT 6.97');
    expect(m?.call).toMatchObject({ title: 'BROKE $6.00 · NEXT 6.97', tone: 'go', ping: true });
    expect(m?.call?.detail).toMatch(/Raise the stop to 5.95, 5c under \$6.00\?/);
  });

  it('a flush is SELL NOW in trial on Paper, a description on Live, and not in the first 10 s', () => {
    const flush = { at: APUS_HELD_NOW - 1, score: -0.62, label: 'flush' };
    const paper = momentOf(at({ flush }));
    expect(paper?.call).toMatchObject({ title: 'SELL NOW · FLUSH · IN TRIAL T1', tone: 'stop', ping: true });
    expect(paper?.call?.detail).toMatch(/never an order/);
    const live = momentOf(at({ flush, who: pfsaView('signal', { venue: 'live' }) }));
    expect(live?.call).toMatchObject({ title: 'FLUSH ON THE TAPE · IN TRIAL T1', ping: false });
    expect(momentOf(at({ flush }, APUS_HELD_NOW - 5))?.call?.title).not.toMatch(/FLUSH/);
    expect(momentOf(at({ flush: { ...flush, at: APUS_HELD_NOW - 10 } }))?.call?.title).not.toMatch(/FLUSH/);
  });

  it('judges the stop and target from the read, and a moved stop starts its watch again', () => {
    const printed = momentOf(inputs({ read: read(), ...holding, last: 5.4, now: APUS_HELD_NOW },
      { ...NO_HELD, since: APUS_HELD_SINCE, stopAt: APUS_HELD_NOW - 1, stopFor: 5.45, targetFor: 5.965 }));
    expect(printed?.call?.title).toBe('SELL NOW · STOP 5.45');
  });

  it('says Nova holds the exit while it does', () => {
    const trade = { kind: 'exit', state: 'holding', exits: 'nova', stop: 5.95, target: null, fill_price: 5.075,
      qty: 100, filled_at: APUS_HELD_NOW - 100, sent_at: APUS_HELD_NOW - 100, trail: true, raised: [] };
    const nova = read({ held: normalizeHeld({ ...apusHeldWire, raise: null,
      stop: { price: 5.95, source: 'nova', rule: "Nova's resting stop" } }) });
    const m = momentOf(inputs({ read: nova, who: pfsaView('signal', { trade: trade as never }), ...holding,
      now: APUS_HELD_NOW }, { ...NO_HELD, since: APUS_HELD_SINCE }));
    expect(m).toMatchObject({ step: 2, exitLabel: 'Target / stop' });
    expect(m?.badge).toMatch(/^NOVA HOLDS THE EXIT/);
  });
});
