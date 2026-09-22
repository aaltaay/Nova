import { describe, expect, it } from 'vitest';
import { ORDER_SESSION_PRACTICE } from '../constantGroups/order_display';
import {
  formatOrderDateTime,
  formatOrderSession,
  formatOrderSide,
  formatOrderStatus,
  formatOrderType,
  orderSideClass,
  orderSideRowClass,
  plausiblePrice,
} from './orderDisplay';
import { orderIdentityKey, orderRowKeys, uniqueOrders } from './orderIdentity';

describe('order display helpers take whatever the wire sent (C2)', () => {
  it('never throws on null or non-string fields', () => {
    expect(formatOrderSide(null)).toBe('—');
    expect(orderSideClass(undefined)).toBe('');
    expect(orderSideRowClass(5)).toBe('');
    expect(formatOrderType(null)).toBe('—');
    expect(formatOrderStatus(null, 0, 1)).toBe('—');
    expect(formatOrderDateTime(1_790_000_000)).toBe('—');
    expect(formatOrderDateTime(null)).toBe('—');
  });
});

describe('IB unset prices (C28)', () => {
  it('reads 1.797e308 and other placeholders as no price', () => {
    expect(plausiblePrice(1.7976931348623157e308)).toBeNull();
    expect(plausiblePrice(0)).toBeNull();
    expect(plausiblePrice(-1)).toBeNull();
    expect(plausiblePrice(Number.NaN)).toBeNull();
    expect(plausiblePrice('8.86')).toBeNull();
    expect(plausiblePrice(8.86)).toBe(8.86);
  });
});

describe('practice orders work in every session (C30)', () => {
  it('says so instead of "Extended hours"', () => {
    expect(formatOrderSession({ outside_rth: true, venue: 'paper' }).label).toBe(ORDER_SESSION_PRACTICE);
    expect(formatOrderSession({ outside_rth: true, fill_estimated: true }).label).toBe(ORDER_SESSION_PRACTICE);
    expect(formatOrderSession({ outside_rth: true }).label).toBe('Extended hours');
    expect(formatOrderSession({ outside_rth: false }).label).toBe('Regular hours');
  });
});

describe('order identity (C29)', () => {
  const completed = (perm: number) => ({ order_id: 0, perm_id: perm, symbol: 'GRML', side: 'BUY' as const });

  it('four completed IB orders with orderId 0 stay four rows', () => {
    const rows = [completed(1), completed(2), completed(3), completed(4)];
    expect(uniqueOrders(rows)).toHaveLength(4);
    expect(new Set(orderRowKeys(rows)).size).toBe(4);
  });

  it('the same order in both lists is one row', () => {
    const working = { order_id: 5, perm_id: 9, symbol: 'GDC', side: 'BUY' as const };
    expect(uniqueOrders([working, { ...working, status: 'Filled' }])).toHaveLength(1);
  });

  it('practice ids that repeat across venues are different orders', () => {
    const paper = { order_id: 1, perm_id: 1, symbol: 'GDC', side: 'BUY' as const, venue: 'paper' as const };
    const sim = { ...paper, venue: 'sim' as const };
    expect(orderIdentityKey(paper)).not.toBe(orderIdentityKey(sim));
  });

  it('a genuine repeat still gets a unique React key', () => {
    const row = completed(7);
    expect(orderRowKeys([row, row])).toEqual(['perm::7', 'perm::7#1']);
  });
});
