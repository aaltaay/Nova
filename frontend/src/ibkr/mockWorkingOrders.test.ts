import { describe, expect, it } from 'vitest';
import { buildMockWorkingOrders } from './mockWorkingOrders';

describe('buildMockWorkingOrders', () => {
  it('returns five paper-style rows for the symbol', () => {
    const rows = buildMockWorkingOrders('sdot');
    expect(rows).toHaveLength(5);
    expect(rows.every((r) => r.symbol === 'SDOT')).toBe(true);
    expect(rows.map((r) => r.order_id)).toEqual([
      90001, 90002, 90003, 90004, 90005,
    ]);
    expect(rows.some((r) => r.order_type === 'STP')).toBe(true);
    expect(rows.some((r) => (r.filled_qty ?? 0) > 0)).toBe(true);
  });
});
