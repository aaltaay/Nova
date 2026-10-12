/**
 * A big seller on the ask, a big buyer on the bid (#846), pure: the wire, the held card's line -- the call, its end
 * (taken, pulled, out of view), that none is there, and why there is no read -- and the chart's call beside a
 * raise. A 20,000-share offer at 4.50 over a 4.47 price; RDYN short 416 for the bid mirror.
 */
import { describe, expect, it } from 'vitest';
import { bigLine, heldWords, normalizeBigWalls, pastWords, type BigWalls } from './bigSeller';
import { bigCall, heldCall } from './heldCalls';
import { RDYN_SHORT_NOW, RDYN_SHORT_SINCE, rdynShortWire } from './heldFixtures';
import { normalizeHeld } from './heldRead';
import { NO_HELD, type MomentInputs } from './momentModel';
import { momentOfSides } from './momentShort';
import { inputs, pfsaRead, pfsaView } from './whoTradesFixtures';

const T = 1_791_382_000;

function wall(over: Record<string, unknown> = {}) {
  return {
    id: `${T}000-TEST-ask-4.5`, kind: 'big_seller', side: 'ask', price: 4.5, state: 'holding', size_first: 22_000,
    size_now: 20_000, size_peak: 22_000, traded: 0, median_level: 550, multiple: 36.4, first_seen_ts: T,
    seen_from_start: false, called_ts: T + 3, ended_ts: null, held_sec: 42, distance: 0.03, distance_pct: 0.67,
    how: null, left: null, ...over,
  };
}

function wire(over: Record<string, unknown> = {}) {
  return {
    schema_version: 1, symbol: 'TEST', source: 'live', as_of: T + 42, watching: true, reason: null, last: 4.47,
    reference: 4.47, reference_source: 'last', window: 0.05, sellers: [wall()], buyers: [],
    sides: { ask: { levels: 5, enough: true }, bid: { levels: 4, enough: true } }, rule: {}, note: '', ...over,
  };
}

const read = (over: Record<string, unknown> = {}): BigWalls => normalizeBigWalls(wire(over))!;

describe('the wire', () => {
  it('reads a reading, and nothing from an unknown schema or a payload that is not one', () => {
    const r = read();
    expect(r.watching).toBe(true);
    expect(r.sellers[0]).toMatchObject({ price: 4.5, state: 'holding', sizeNow: 20_000, sizeFirst: 22_000, heldSec: 42,
      distance: 0.03, seenFromStart: false });
    expect(normalizeBigWalls({ ...wire(), schema_version: 2 })).toBeNull();
    expect(normalizeBigWalls({ watching: true })).toBeNull();
    expect(read({ sellers: [{ price: 4.5, state: 'invented', first_seen_ts: T }] }).sellers).toEqual([]);
  });
});

describe('the held card line', () => {
  it('calls a big seller: size, price, cents over and how long it has held', () => {
    const line = bigLine(read(), false);
    expect(line.tone).toBe('warn');
    expect(line.text).toBe('BIG SELLER 20,000 @ 4.50 · 3¢ over · held 42 s');
    expect(line.detail).toMatch(/36x the other asks, 3¢ over; there since .*, first seen at 22,000\. Shown, never acted on\./);
  });

  it('says "3 min+" for a size there before the first book Nova read, and "at the price" for one at it', () => {
    expect(heldWords(200, true)).toBe('3 min+');
    expect(pastWords(0, 4.5, 'over')).toBe('at the price');
    expect(pastWords(0.004, 0.52, 'over')).toBe('0.40¢ over');
    expect(bigLine(read({ sellers: [wall({ seen_from_start: true, held_sec: 200 })] }), false).text).toContain('held 3 min+');
  });

  it('says it left the book, then taken -- the seller is gone -- or pulled', () => {
    expect(bigLine(read({ sellers: [wall({ state: 'left' })] }), false).text).toBe('BIG SELLER @ 4.50 · LEFT THE BOOK');
    const through = bigLine(read({ sellers: [wall({ state: 'eaten', how: 'through', ended_ts: T + 50 })] }), false);
    expect(through.tone).toBe('good');
    expect(through.text).toBe('BIG SELLER @ 4.50 TAKEN');
    expect(through.detail).toMatch(/A print went through 4.50 at .*: the size offered there traded\. The seller is gone\./);
    const traded = bigLine(read({ sellers: [wall({ state: 'eaten', how: 'traded', ended_ts: T + 50,
      left: { before: 15_000, after: 0, filled: 14_000 } })] }), false);
    expect(traded.detail).toMatch(/^14,000 of the 15,000 that left traded at 4.50\. The seller is gone\./);
    const pulled = bigLine(read({ sellers: [wall({ state: 'pulled', how: 'no_prints', ended_ts: T + 50,
      left: { before: 20_000, after: 0, filled: 300 } })] }), false);
    expect(pulled.text).toBe('BIG SELLER @ 4.50 PULLED');
    expect(pulled.detail).toBe('The 20,000 offered at 4.50 left the book with 300 traded there: pulled, not bought. '
      + 'It may come back.');
    const lost = bigLine(read({ sellers: [wall({ state: 'lost', how: 'cut_off', ended_ts: T + 50 })] }), false);
    expect(lost.text).toBe('BIG SELLER @ 4.50 · OUT OF VIEW');
    expect(lost.detail).toMatch(/whether it traded or was pulled is unknown/);
  });

  it('tells the nearest one still there before any that ended', () => {
    const r = read({ sellers: [wall({ price: 4.52, distance: 0.05 }), wall({ state: 'pulled', ended_ts: T + 40 })] });
    expect(bigLine(r, false).text).toContain('@ 4.52');
  });

  it('says none is there on a fresh line, and when the book is too thin to tell', () => {
    expect(bigLine(read({ sellers: [] }), false)).toMatchObject({ tone: 'quiet', text: 'No big seller within 5¢ over the price' });
    const thin = read({ sellers: [], sides: { ask: { levels: 3, enough: false }, bid: { levels: 4, enough: true } } });
    expect(bigLine(thin, false).text).toBe('Too few asks on Level 2 to tell a big seller (3 shown)');
  });

  it('never shows a guess: no line, a stale line, a failed read each say so in plain words', () => {
    const none = bigLine(read({ watching: false, sellers: [],
      reason: 'No Level 2 line for TEST has reached the book watcher' }), false);
    expect(none).toMatchObject({ tone: 'absent', text: 'No read on big sellers', wall: null });
    expect(none.detail).toBe('No Level 2 line for TEST has reached the book watcher');
    const stale = bigLine(read({ watching: false, reason: 'The Level 2 line for TEST has sent no book for 12 s now' }), false);
    expect(stale.text).toBe('No read on big sellers');
    expect(stale.detail).toMatch(/no book for 12 s/);
    expect(bigLine(null, false, 'The big-seller read failed: HTTP 500')).toMatchObject({ tone: 'absent',
      detail: 'The big-seller read failed: HTTP 500' });
    expect(bigLine(null, false).text).toBe('Reading Level 2 for big sellers…');
  });

  it('mirrors for a short: a big buyer on the bid, under the price', () => {
    const r = read({ sellers: [], buyers: [wall({ side: 'bid', kind: 'big_buyer', price: 4.45, distance: 0.02 })] });
    expect(bigLine(r, true).text).toBe('BIG BUYER 20,000 @ 4.45 · 2¢ under · held 42 s');
    expect(bigLine(read({ buyers: [] }), true).text).toBe('No big buyer within 5¢ under the price');
    const taken = read({ sellers: [], buyers: [wall({ side: 'bid', price: 4.45, state: 'eaten', how: 'through',
      ended_ts: T + 50 })] });
    expect(bigLine(taken, true).detail).toMatch(/The buyer is gone\./);
  });
});

describe('the chart call', () => {
  const holdingLong = (over: Partial<MomentInputs> = {}) => inputs({
    read: null, position: { qty: 100, avgCost: 4.4 }, last: 4.47, now: T + 42, big: read(), ...over,
  });

  it('calls BIG SELLER once, pinned at its price, keeping the badge; nothing without a fresh read', () => {
    const said = bigCall(holdingLong(), false)!;
    expect(said.badge).toBeNull();
    expect(said.call).toMatchObject({ id: `big:${T}000-TEST-ask-4.5`, tone: 'wait', ping: true,
      title: 'BIG SELLER 20,000 @ 4.50 · 3¢ over · held 42 s', pin: { label: 'BIG SELLER', price: 4.5, at: null } });
    expect(heldCall(holdingLong())?.call.id).toBe(said.call.id);
    expect(bigCall(holdingLong({ big: read({ watching: false, reason: 'stale' }) }), false)).toBeNull();
    const ended = bigCall(holdingLong({ big: read({ sellers: [wall({ state: 'eaten', how: 'through', ended_ts: T + 40 })] }) }), false)!;
    expect(ended.call).toMatchObject({ id: `big-eaten:${T}000-TEST-ask-4.5`, tone: 'info', ping: false, pin: null });
  });

  it('a held short hears the big buyer when it is newer than the lowered stop offer', () => {
    const lowerAt = normalizeHeld(rdynShortWire)!.lower!.at;
    const buyer = wall({ side: 'bid', kind: 'big_buyer', price: 5.40, distance: 0.06, called_ts: lowerAt + 10 });
    const i = inputs({
      read: { ...pfsaRead('triggered'), symbol: 'RDYN', price: 5.46, plan: null, held: normalizeHeld(rdynShortWire) },
      who: pfsaView('signal'), position: { qty: -416, avgCost: 5.77 }, last: 5.46, now: RDYN_SHORT_NOW,
      big: read({ symbol: 'RDYN', sellers: [], buyers: [buyer] }),
    }, { ...NO_HELD, since: RDYN_SHORT_SINCE });
    const m = momentOfSides(i);
    expect(m?.badge).toBe('SHORT 416 · +$128.96');           // the call keeps the P&L badge
    expect(m?.call?.title).toBe('BIG BUYER 20,000 @ 5.40 · 6¢ under · held 42 s');
    const older = { ...i, big: read({ symbol: 'RDYN', sellers: [], buyers: [{ ...buyer, called_ts: lowerAt - 10 }] }) };
    expect(momentOfSides(older)?.call?.title).toBe('BROKE $5.50 · NEXT 5.35');
  });
});
