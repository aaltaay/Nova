import { describe, expect, it } from 'vitest';
import { buyStopRefusal, riskAtStop, seedBuyStop, shortSubmitLabel } from './shortTicketModel';

describe('a short under $1 keeps its four digits', () => {
  it('does not read a stop just over the limit as the same price', () => {
    expect(buyStopRefusal('0.3456', '0.3499')).toBeNull();
  });

  it('seeds the buy stop on the sub-dollar tick', () => {
    expect(seedBuyStop('0.3456', 0.05)).toBe('0.3956');
  });

  it('says the price it will send', () => {
    expect(shortSubmitLabel({
      ticketSide: 'short', qty: 0, symbol: 'soar', orderQty: '1000', limit: '0.3188', buyStop: '0.3399', orderType: 'LMT',
    })).toContain('1000 @ 0.3188 · stop 0.3399');
  });

  it('counts the risk from the real prices', () => {
    expect(riskAtStop('0.3188', '0.3399', '1000')).toBe(21.1);
  });
});
