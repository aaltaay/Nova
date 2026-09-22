import { describe, expect, it } from 'vitest';
import { estimateTicketCost } from './ticketCost';
import type { ManualOrderValues } from './orderEntry';

const BASE: ManualOrderValues = {
  symbol: 'GRML',
  side: 'BUY',
  orderType: 'LMT',
  quantityMode: 'shares',
  quantityValue: '100',
  limitPrice: '8.90',
  stopPrice: '',
  outsideRth: true,
};

const CTX = { marketReferencePrice: 8.86, buyingPower: 397_354, positionQty: null };

describe('estimateTicketCost', () => {
  it('prices a limit buy at its own limit and subtracts from buying power', () => {
    const est = estimateTicketCost(BASE, CTX, { forceQty: null });
    expect(est).toEqual({
      shares: 100,
      price: 8.9,
      cost: 890,
      buyingPowerAfter: 397_354 - 890,
    });
  });

  it('prices a market order at the reference price', () => {
    const est = estimateTicketCost({ ...BASE, orderType: 'MKT' }, CTX, { forceQty: null });
    expect(est.price).toBe(8.86);
    expect(est.cost).toBeCloseTo(886, 6);
  });

  it('a sell of a held long frees buying power; a short entry consumes it', () => {
    const sell = estimateTicketCost(
      { ...BASE, side: 'SELL' },
      { ...CTX, positionQty: 100 },
      { forceQty: null },
    );
    expect(sell.buyingPowerAfter).toBe(397_354 + 890);
    const short = estimateTicketCost(
      { ...BASE, side: 'SELL', shortEntry: true },
      CTX,
      { forceQty: null },
    );
    expect(short.buyingPowerAfter).toBe(397_354 - 890);
  });

  it('is a stated absence, never a guess, when the ticket cannot size or price', () => {
    expect(estimateTicketCost({ ...BASE, quantityValue: '' }, CTX, { forceQty: null })).toEqual({
      shares: null,
      price: null,
      cost: null,
      buyingPowerAfter: null,
    });
    const noPrice = estimateTicketCost(
      { ...BASE, orderType: 'MKT' },
      { ...CTX, marketReferencePrice: null },
      { forceQty: null },
    );
    expect(noPrice.shares).toBe(100);
    expect(noPrice.cost).toBeNull();
    const noBp = estimateTicketCost(BASE, { ...CTX, buyingPower: null }, { forceQty: null });
    expect(noBp.cost).toBe(890);
    expect(noBp.buyingPowerAfter).toBeNull();
  });

  it('follows the forced share quantity when sizing is locked', () => {
    const est = estimateTicketCost(BASE, CTX, { forceQty: 1 });
    expect(est.shares).toBe(1);
    expect(est.cost).toBe(8.9);
  });
});
