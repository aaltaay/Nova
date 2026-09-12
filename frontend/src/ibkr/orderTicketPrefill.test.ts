/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from 'vitest';
import {
  parseOrderTicketPrefill,
  requestOrderTicketPrefill,
  subscribeOrderTicketPrefill,
} from './orderTicketPrefill';

const BUY_SMPL = {
  symbol: 'SMPL',
  side: 'BUY' as const,
  orderType: 'LMT' as const,
  quantityValue: '100',
  limitPrice: '4.25',
};

describe('parseOrderTicketPrefill', () => {
  it('uppercases the symbol and keeps the staged fields', () => {
    expect(parseOrderTicketPrefill({ ...BUY_SMPL, symbol: ' smpl ' })).toEqual(BUY_SMPL);
  });

  it('rejects junk, unknown sides and limit orders with no price', () => {
    expect(parseOrderTicketPrefill(null)).toBeNull();
    expect(parseOrderTicketPrefill({ ...BUY_SMPL, symbol: '' })).toBeNull();
    expect(parseOrderTicketPrefill({ ...BUY_SMPL, side: 'SHORT' })).toBeNull();
    expect(parseOrderTicketPrefill({ ...BUY_SMPL, orderType: 'TRAIL' })).toBeNull();
    expect(parseOrderTicketPrefill({ ...BUY_SMPL, quantityValue: '' })).toBeNull();
    expect(parseOrderTicketPrefill({ ...BUY_SMPL, limitPrice: '' })).toBeNull();
  });
});

describe('subscribeOrderTicketPrefill', () => {
  it('delivers only requests for the subscribed symbol', () => {
    const smpl = vi.fn();
    const other = vi.fn();
    const offSmpl = subscribeOrderTicketPrefill('smpl', smpl);
    const offOther = subscribeOrderTicketPrefill('AAPL', other);

    requestOrderTicketPrefill(BUY_SMPL);

    expect(smpl).toHaveBeenCalledWith(BUY_SMPL);
    expect(other).not.toHaveBeenCalled();
    offSmpl();
    offOther();
  });

  it('stops delivering after unsubscribe', () => {
    const handler = vi.fn();
    subscribeOrderTicketPrefill('SMPL', handler)();
    requestOrderTicketPrefill(BUY_SMPL);
    expect(handler).not.toHaveBeenCalled();
  });

  it('drops malformed requests instead of dispatching them', () => {
    const handler = vi.fn();
    const off = subscribeOrderTicketPrefill('SMPL', handler);
    requestOrderTicketPrefill({ ...BUY_SMPL, limitPrice: '' });
    expect(handler).not.toHaveBeenCalled();
    off();
  });
});
