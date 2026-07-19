import { describe, expect, it } from 'vitest';
import { buildMockClosedOrders } from './mockClosedOrders';

describe('buildMockClosedOrders', () => {
  it('uppercases symbol and includes filled + cancelled rows', () => {
    const rows = buildMockClosedOrders('sdot');
    expect(rows.some((r) => r.symbol === 'SDOT' && r.status === 'Filled')).toBe(true);
    expect(rows.some((r) => r.status === 'Cancelled')).toBe(true);
  });
});
