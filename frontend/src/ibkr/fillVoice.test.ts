import { describe, expect, it } from 'vitest';
import { newFillVoiceState, readFills, spellTicker, type FillVoiceSnap } from './fillVoice';
import type { IbkrOrder } from './types';

function order(over: Partial<IbkrOrder> & { leg_role?: string | null } = {}): IbkrOrder {
  return {
    order_id: 7,
    symbol: 'SOFI',
    side: 'BUY',
    qty: 100,
    filled_qty: 0,
    order_type: 'LMT',
    limit_price: 14.0,
    status: 'Submitted',
    ...over,
  } as IbkrOrder;
}

function snap(orders: IbkrOrder[], closedOrders: IbkrOrder[] = [], over: Partial<FillVoiceSnap> = {}): FillVoiceSnap {
  return { venue: 'paper', ordersRead: true, orders, closedOrders, ...over };
}

/** A state seeded on an empty venue, so the next read's fills are news. */
function seeded() {
  const state = newFillVoiceState();
  expect(readFills(state, snap([]))).toEqual([]);
  return state;
}

describe('fillVoice', () => {
  it('spells a ticker letter by letter', () => {
    expect(spellTicker('sofi')).toBe('S O F I');
    expect(spellTicker('BRK.B')).toBe('B R K dot B');
  });

  it('says a buy that filled, once', () => {
    const state = seeded();
    const filled = order({ filled_qty: 100, status: 'Filled' });
    expect(readFills(state, snap([], [filled]))).toEqual(['Bought 100 shares of S O F I.']);
    expect(readFills(state, snap([], [filled]))).toEqual([]);
  });

  it('says thousands and one share the way they are heard', () => {
    const state = seeded();
    expect(readFills(state, snap([], [order({ qty: 1000, filled_qty: 1000 })]))).toEqual(['Bought 1,000 shares of S O F I.']);
    expect(readFills(state, snap([], [order({ order_id: 8, side: 'SELL', qty: 1, filled_qty: 1 })])))
      .toEqual(['Sold 1 share of S O F I.']);
  });

  it('never says the fills already on the rows when a venue is first read', () => {
    const state = newFillVoiceState();
    expect(readFills(state, snap([], [order({ filled_qty: 100 })]))).toEqual([]);
    // A fill that grows after the seed is news; the seeded shares are not said again.
    expect(readFills(state, snap([order({ qty: 300, filled_qty: 250 })]))).toEqual(['Bought 150 shares of S O F I, partial.']);
  });

  it('waits for both order lists before seeding', () => {
    const state = newFillVoiceState();
    expect(readFills(state, snap([], [order({ filled_qty: 100 })], { ordersRead: false }))).toEqual([]);
    expect(state.seeded).toBe(false);
    expect(readFills(state, snap([], [order({ filled_qty: 100 })]))).toEqual([]);
    expect(state.seeded).toBe(true);
  });

  it('seeds again on a venue change', () => {
    const state = seeded();
    const live = order({ order_id: 7, filled_qty: 100 });
    expect(readFills(state, snap([], [live], { venue: 'live' }))).toEqual([]);
    expect(readFills(state, snap([], [live], { venue: 'live' }))).toEqual([]);
  });

  it('names a sell, a short and a cover', () => {
    const state = seeded();
    expect(readFills(state, snap([], [
      order({ order_id: 1, side: 'SELL', filled_qty: 100 }),
      order({ order_id: 2, symbol: 'GME', side: 'SELL', short_entry: true, filled_qty: 200 }),
      order({ order_id: 3, symbol: 'AMC', side: 'BUY', effect: 'closes', position_side: 'short', filled_qty: 50 }),
    ]))).toEqual([
      'Sold 100 shares of S O F I.',
      'Shorted 200 shares of G M E.',
      'Covered 50 shares of A M C.',
    ]);
  });

  it('says who sent it and why: bot, flatten, stop, target', () => {
    const state = seeded();
    expect(readFills(state, snap([], [
      order({ order_id: 1, bot_id: 'l2-first-pullback', filled_qty: 100 }),
      order({ order_id: 2, symbol: 'GME', side: 'SELL', order_origin: 'ticket_flatten', order_type: 'MKT', filled_qty: 300 }),
    ]))).toEqual([
      'Bot bought 100 shares of S O F I.',
      'Flatten. Sold 300 shares of G M E.',
    ]);
    expect(readFills(state, snap([], [
      order({ order_id: 3, side: 'SELL', order_type: 'STP', filled_qty: 100 }),
      order({ order_id: 4, symbol: 'AMC', side: 'SELL', leg_role: 'target', filled_qty: 50 }),
      order({ order_id: 5, symbol: 'GME', side: 'SELL', order_type: 'STP', order_origin: 'bot', filled_qty: 20 }),
    ]))).toEqual([
      'Stop hit. Sold 100 shares of S O F I.',
      'Target hit. Sold 50 shares of A M C.',
      'Stop hit. Bot sold 20 shares of G M E.',
    ]);
  });

  it('says the daily loss limit\'s sell as the loss limit, never as the bot (ADR 056)', () => {
    const state = seeded();
    expect(readFills(state, snap([], [
      order({ order_id: 1, symbol: 'WETO', side: 'SELL', qty: 10_000, order_type: 'MKT', order_origin: 'loss_limit',
        order_source: 'flatten', filled_qty: 10_000 }),
      // A bot's position: the loss limit sold it, so it is still not "Bot sold".
      order({ order_id: 2, symbol: 'GME', side: 'SELL', order_type: 'MKT', order_origin: 'loss_limit',
        order_source: 'flatten', bot_id: 'l2-first-pullback', filled_qty: 20 }),
      order({ order_id: 3, symbol: 'AMC', side: 'BUY', order_type: 'MKT', order_origin: 'loss_limit',
        order_source: 'flatten', filled_qty: 50 }),
    ]))).toEqual([
      'Loss limit. Sold 10,000 shares of W E T O.',
      'Loss limit. Sold 20 shares of G M E.',
      'Loss limit. Covered 50 shares of A M C.',
    ]);
  });

  it('reads the retired loss rules\' old rows as flattens, never as the bot', () => {
    const state = seeded();
    const said = readFills(state, snap([], [
      order({ order_id: 1, symbol: 'WETO', side: 'SELL', qty: 10_000, order_type: 'MKT', order_origin: 'bot_trip',
        order_source: 'flatten', filled_qty: 10_000 }),
      order({ order_id: 2, symbol: 'GME', side: 'SELL', order_type: 'MKT', order_origin: 'all_stop',
        order_source: 'flatten', filled_qty: 20 }),
    ]));
    expect(said).toEqual(['Flatten. Sold 10,000 shares of W E T O.', 'Flatten. Sold 20 shares of G M E.']);
    expect(said.join(' ')).not.toMatch(/Bot sold/);
  });

  it('never calls a buy stop that opens a stop-out', () => {
    const state = seeded();
    expect(readFills(state, snap([], [order({ order_type: 'STP', filled_qty: 100 })])))
      .toEqual(['Bought 100 shares of S O F I.']);
  });

  it('says partial while the order still works, and the rest when it fills', () => {
    const state = seeded();
    expect(readFills(state, snap([order({ qty: 1000, filled_qty: 300 })]))).toEqual(['Bought 300 shares of S O F I, partial.']);
    expect(readFills(state, snap([], [order({ qty: 1000, filled_qty: 1000, status: 'Filled' })])))
      .toEqual(['Bought 700 shares of S O F I.']);
  });

  it('reads an order in both lists once, at its larger fill', () => {
    const state = seeded();
    expect(readFills(state, snap([order({ filled_qty: 40 })], [order({ filled_qty: 100 })])))
      .toEqual(['Bought 100 shares of S O F I.']);
  });

  it('adds fills of one symbol and one sentence in one read', () => {
    const state = seeded();
    expect(readFills(state, snap([], [
      order({ order_id: 1, filled_qty: 100 }),
      order({ order_id: 2, filled_qty: 200 }),
    ]))).toEqual(['Bought 300 shares of S O F I.']);
  });

  it('never speaks shares a Sim rewind takes back, and says them when they fill again', () => {
    const state = seeded();
    expect(readFills(state, snap([], [order({ filled_qty: 100 })]))).toHaveLength(1);
    expect(readFills(state, snap([order({ filled_qty: 0 })]))).toEqual([]);
    expect(readFills(state, snap([], [order({ filled_qty: 100 })]))).toEqual(['Bought 100 shares of S O F I.']);
  });

  it('counts the rest past three sentences', () => {
    const state = seeded();
    const rows = ['AAA', 'BBB', 'CCC', 'DDD', 'EEE'].map((symbol, i) => order({ order_id: i + 1, symbol, filled_qty: 10 }));
    expect(readFills(state, snap([], rows))).toEqual([
      'Bought 10 shares of A A A.',
      'Bought 10 shares of B B B.',
      'And 3 more fills.',
    ]);
  });

  it('keys an order IBKR knows only by its permId', () => {
    const state = seeded();
    const recovered = order({ order_id: 0, perm_id: 99, filled_qty: 100, source: 'ib_recovered' });
    expect(readFills(state, snap([], [recovered]))).toEqual(['Bought 100 shares of S O F I.']);
    expect(readFills(state, snap([], [recovered]))).toEqual([]);
  });
});
