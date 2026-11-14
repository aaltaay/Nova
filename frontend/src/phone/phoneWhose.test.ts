import { describe, expect, it } from 'vitest';
import type { HistoryFill } from '../account/accountHistoryTypes';
import type { PracticePosition } from '../practice/practiceTypes';
import { fillWhose, orderWhose, ownerOf, positionWhose, whoChip, whoseFillRows, type Whose } from './phoneWhose';

const whose = (over: Partial<Whose>): Whose => ({ owner: 'you', bot: null, handed: false, closedByYou: false, ...over });

const fill = (over: Partial<HistoryFill> = {}): HistoryFill => ({
  ts: 1_000, order_id: 1, symbol: 'ABCD', side: 'SELL', qty: 100, price: 4.5, source: 'manual', bot_id: null,
  commission: 1, fees: 0, realized: 10, fill_estimated: true, fill_basis: 'quote', ...over,
});

describe('the who-chip says whose a row is', () => {
  it("names each book in the phone's short words", () => {
    expect(whoChip(whose({ owner: 'you' })).text).toBe('You');
    expect(whoChip(whose({ owner: 'claude' })).text).toBe('Claude');
    expect(whoChip(whose({ owner: 'brain' })).text).toBe('Brain');
    expect(whoChip(whose({ owner: 'earlier_bots', bot: 'first_pullback' })).text).toBe('Earlier');
  });

  it("titles the chip with the book's full name, and a retired bot's own name inside Earlier bots", () => {
    expect(whoChip(whose({ owner: 'brain' })).title).toBe('The brain');
    expect(whoChip(whose({ owner: 'earlier_bots', bot: 'auto_entry' })).title).toBe('Auto-entry');
  });

  it("reads Handed on a trader's shares handed to you, and says they are yours to close", () => {
    expect(whoChip(whose({ owner: 'brain', handed: true }))).toEqual({ text: 'Handed', title: "The brain's · yours to close" });
  });

  it('reads Handed on your close of handed shares, booked on the trader that held them', () => {
    expect(whoChip(whose({ owner: 'claude', handed: true, closedByYou: true }))).toEqual({ text: 'Handed', title: 'Claude · closed by you' });
  });

  it("says Nova for one of Nova's own closes", () => {
    expect(whoChip(whose({ owner: null })).text).toBe('Nova');
  });
});

describe('whose a position, an order and a fill are', () => {
  const ledger: PracticePosition[] = [{
    symbol: 'xlab', qty: 300, avg_cost: 4.3, mark: 4.5, unrealized: 60,
    by_owner: [
      { owner: 'you', bot: null, qty: 100, avg_cost: 4.3, unrealized_pnl: 20 },
      { owner: 'brain', bot: null, qty: 200, avg_cost: 4.32, unrealized_pnl: 40, handed: true },
    ],
  }];

  it("takes a holder's handed flag from the ledger", () => {
    expect(positionWhose({ symbol: 'XLAB', owner: 'brain', bot: null }, ledger)).toEqual(whose({ owner: 'brain', handed: true }));
    expect(positionWhose({ symbol: 'XLAB', owner: 'you', bot: null }, ledger)).toEqual(whose({ owner: 'you' }));
  });

  it('says nothing for a row that names no book, or a book that is gone', () => {
    expect(positionWhose({ symbol: 'XLAB' }, ledger)).toBeNull();
    expect(ownerOf('bots')).toBeNull();
  });

  it("reads an order's book, Nova for a null owner, nothing when the wire did not say", () => {
    expect(orderWhose({ owner: 'claude', bot: null })).toEqual(whose({ owner: 'claude' }));
    expect(orderWhose({ owner: null })).toEqual(whose({ owner: null }));
    expect(orderWhose({})).toBeNull();
  });

  it("gives a fill its order's book", () => {
    expect(fillWhose(fill({ owner: 'claude', bot: null, parts: [] }))).toEqual(whose({ owner: 'claude' }));
    expect(fillWhose(fill({ owner: 'earlier_bots', bot: 'bot_api' }))).toEqual(whose({ owner: 'earlier_bots', bot: 'bot_api' }));
    expect(fillWhose(fill())).toBeNull();
  });

  it('gives your close of handed shares to the trader that held them', () => {
    const closed = fill({
      owner: 'you', bot: null, closed_by: 'you',
      parts: [
        { owner: 'you', bot: null, qty: 100, closes: true, realized: 2, commission: 0.5, fees: 0 },
        { owner: 'brain', bot: null, qty: 200, closes: true, realized: 8, commission: 0.5, fees: 0, closed_by: 'you' },
      ],
    });
    expect(fillWhose(closed)).toEqual(whose({ owner: 'brain', handed: true, closedByYou: true }));
  });

  it('lists fills newest first, each saying whose, the same fill twice kept apart', () => {
    const rows = whoseFillRows([
      fill({ ts: 10, owner: 'you', bot: null }),
      fill({ ts: 30, owner: 'claude', bot: null }),
      fill({ ts: 30, owner: 'claude', bot: null }),
    ]);
    expect(rows.map((r) => [r.ts, r.whose?.owner])).toEqual([[30, 'claude'], [30, 'claude'], [10, 'you']]);
    expect(new Set(rows.map((r) => r.key)).size).toBe(3);
    expect(rows[2]).toMatchObject({ symbol: 'ABCD', side: 'SELL', qty: 100, price: 4.5, estimated: true });
  });
});
