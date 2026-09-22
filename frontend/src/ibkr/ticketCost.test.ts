import { describe, expect, it } from 'vitest';
import { PRACTICE_NO_SHORTS_REASON } from '../constantGroups/practice';
import { TICKET_COST_NO_POSITION } from '../constantGroups/trader_chrome';
import { SIM_REPLAY_PRICE_NONE } from '../sim/simConstants';
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

  it('a SELL from flat or past the held quantity frees nothing -- it would be refused (V24)', () => {
    for (const positionQty of [null, 0, -50]) {
      const est = estimateTicketCost({ ...BASE, side: 'SELL' }, { ...CTX, positionQty }, { forceQty: null });
      expect(est.cost).toBeNull();
      expect(est.buyingPowerAfter).toBeNull();
      expect(est.note).toBe(TICKET_COST_NO_POSITION);
    }
    const over = estimateTicketCost({ ...BASE, side: 'SELL' }, { ...CTX, positionQty: 40 }, { forceQty: null });
    expect(over.buyingPowerAfter).toBeNull();
    expect(over.note).toBe(TICKET_COST_NO_POSITION);
  });

  it('a practice venue refuses the short entry a Live margin account may open', () => {
    const short = { ...BASE, side: 'SELL' as const, shortEntry: true };
    const practice = estimateTicketCost(short, CTX, { forceQty: null }, { practice: true });
    expect(practice.buyingPowerAfter).toBeNull();
    expect(practice.note).toBe(PRACTICE_NO_SHORTS_REASON);
    expect(estimateTicketCost(short, CTX, { forceQty: null }, { practice: false }).buyingPowerAfter).toBe(397_354 - 890);
  });

  it('says why there is no market price when the venue knows (Sim off the edge)', () => {
    const est = estimateTicketCost(
      { ...BASE, orderType: 'MKT' },
      { ...CTX, marketReferencePrice: null },
      { forceQty: null },
      { practice: true, priceNote: SIM_REPLAY_PRICE_NONE },
    );
    expect(est.cost).toBeNull();
    expect(est.note).toBe(SIM_REPLAY_PRICE_NONE);
    // A limit is priced at its own limit whatever the venue's reference.
    expect(estimateTicketCost(BASE, { ...CTX, marketReferencePrice: null }, { forceQty: null },
      { practice: true, priceNote: SIM_REPLAY_PRICE_NONE }).cost).toBe(890);
  });

  it('prices a Market order at the far side of the quote, where it fills (QA R36)', () => {
    // Capture at 12:36: last 8.82, bid 8.81, ask 8.84 -- the buy fills at the ask.
    const mkt = { ...BASE, orderType: 'MKT' as const };
    const buy = estimateTicketCost(mkt, { ...CTX, marketReferencePrice: 8.82 }, { forceQty: null }, { marketFillPrice: 8.84 });
    expect(buy.price).toBe(8.84);
    expect(buy.cost).toBeCloseTo(884, 6);
    // A limit stays at its limit; no quote leaves the Market order at the reference.
    expect(estimateTicketCost(BASE, CTX, { forceQty: null }, { marketFillPrice: 8.84 }).price).toBe(8.9);
    expect(estimateTicketCost(mkt, { ...CTX, marketReferencePrice: 8.82 }, { forceQty: null }, { marketFillPrice: null }).price).toBe(8.82);
  });

  it('on a practice venue BP after follows the ledger: fees out of equity, the fill re-marks the position (QA W28)', () => {
    const buy = estimateTicketCost(
      { ...BASE, symbol: 'TOPS', limitPrice: '1.49' },
      { marketReferencePrice: 1.49, buyingPower: 399_573, positionQty: null },
      { forceQty: null },
      { practice: true, ledger: { netLiquidation: 100_020, grossPositionValue: 507, heldMark: null } },
    );
    // (100,020 - $1.00 commission) x 4 - (507 + 149) = 399,420
    expect(buy.buyingPowerAfter).toBeCloseTo(399_420, 6);
    // Live keeps IBKR's own rule out of reach: BP - cost.
    const live = estimateTicketCost(
      { ...BASE, symbol: 'TOPS', limitPrice: '1.49' },
      { marketReferencePrice: 1.49, buyingPower: 399_573, positionQty: null },
      { forceQty: null },
      { practice: false, ledger: { netLiquidation: 100_020, grossPositionValue: 507, heldMark: null } },
    );
    expect(live.buyingPowerAfter).toBeCloseTo(399_573 - 149, 6);
  });
});
