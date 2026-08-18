import { describe, expect, it } from 'vitest';
import { formatClosedOrderId } from './formatClosedOrderId';

describe('formatClosedOrderId', () => {
  it('shows a real session order id', () => {
    expect(formatClosedOrderId({ order_id: 19112 })).toBe('19112');
  });

  it('shows permId when session id is zero', () => {
    expect(formatClosedOrderId({ order_id: 0, perm_id: 888001 })).toBe('888001');
  });

  it('shows -- when IB replay has no usable id', () => {
    expect(formatClosedOrderId({ order_id: 0 })).toBe('--');
    expect(formatClosedOrderId({ order_id: 0, perm_id: 0 })).toBe('--');
  });
});
