import { describe, expect, it } from 'vitest';
import { formatActivityOrderRef, formatActivityQty } from './formatActivity';

describe('formatActivityQty', () => {
  it('shows the clamp when requested and sent differ', () => {
    expect(formatActivityQty({ requested_qty: 10, sent_qty: 1 })).toBe('10 -> 1');
  });

  it('shows one number when they match', () => {
    expect(formatActivityQty({ requested_qty: 1, sent_qty: 1 })).toBe('1');
  });
});

describe('formatActivityOrderRef', () => {
  it('prefers session order id, then permId', () => {
    expect(formatActivityOrderRef({ order_id: 19112, perm_id: 9 })).toBe('19112');
    expect(formatActivityOrderRef({ order_id: 0, perm_id: 888001 })).toBe('888001');
    expect(formatActivityOrderRef({ order_id: 0, perm_id: 0 })).toBe('--');
  });
});
