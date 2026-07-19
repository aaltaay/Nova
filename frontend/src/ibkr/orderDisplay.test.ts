import { describe, expect, it } from 'vitest';
import {
  formatExtendedHours,
  formatOrderSide,
  formatOrderStatus,
  formatOrderType,
  orderStatusTone,
} from './orderDisplay';

describe('orderDisplay', () => {
  it('spells out sides and order types', () => {
    expect(formatOrderSide('BUY')).toBe('Buy');
    expect(formatOrderSide('SELL')).toBe('Sell');
    expect(formatOrderType('LMT')).toBe('Limit Order');
    expect(formatOrderType('MKT')).toBe('Market Order');
    expect(formatOrderType('STP')).toBe('Stop Order');
    expect(formatOrderType('STP LMT')).toBe('Stop Limit Order');
  });

  it('maps IBKR statuses to Webull-clean labels', () => {
    expect(formatOrderStatus('PreSubmitted', 0, 100)).toBe('Pending');
    expect(formatOrderStatus('PendingSubmit', 0, 25)).toBe('Pending');
    expect(formatOrderStatus('Submitted', 0, 100)).toBe('Working');
    expect(formatOrderStatus('Submitted', 20, 50)).toBe('Partially filled');
    expect(formatOrderStatus('Filled', 100, 100)).toBe('Filled');
    expect(formatOrderStatus('Cancelled', 0, 100)).toBe('Cancelled');
    expect(formatOrderStatus('Inactive', 0, 100)).toBe('Failed');
  });

  it('labels session and status tone', () => {
    expect(formatExtendedHours(true)).toBe('Extended hours');
    expect(formatExtendedHours(false)).toBe('Regular hours');
    expect(orderStatusTone('Working')).toBe('working');
    expect(orderStatusTone('Partially filled')).toBe('partial');
  });
});
