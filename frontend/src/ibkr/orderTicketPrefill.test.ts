/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from 'vitest';
import {
  orderTicketListening,
  parseOrderTicketPrefill,
  requestOrderTicketPrefill,
  subscribeOrderTicketPrefill,
  watchOrderTicketListening,
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

describe('orderTicketListening (#566)', () => {
  it('is true only while a ticket for that symbol is subscribed', () => {
    expect(orderTicketListening('SMPL')).toBe(false);
    const off = subscribeOrderTicketPrefill('smpl', vi.fn());
    expect(orderTicketListening('SMPL')).toBe(true);
    expect(orderTicketListening(' smpl ')).toBe(true);
    expect(orderTicketListening('AAPL')).toBe(false);
    off();
    expect(orderTicketListening('SMPL')).toBe(false);
  });

  it('counts tickets, so one of two leaving keeps the symbol listening', () => {
    const offA = subscribeOrderTicketPrefill('SMPL', vi.fn());
    const offB = subscribeOrderTicketPrefill('SMPL', vi.fn());
    offA();
    offA();
    expect(orderTicketListening('SMPL')).toBe(true);
    offB();
    expect(orderTicketListening('SMPL')).toBe(false);
  });

  it('tells watchers when a ticket starts and stops listening', () => {
    const watcher = vi.fn();
    const unwatch = watchOrderTicketListening(watcher);
    const off = subscribeOrderTicketPrefill('SMPL', vi.fn());
    expect(watcher).toHaveBeenCalledTimes(1);
    off();
    expect(watcher).toHaveBeenCalledTimes(2);
    unwatch();
    subscribeOrderTicketPrefill('SMPL', vi.fn())();
    expect(watcher).toHaveBeenCalledTimes(2);
  });
});
