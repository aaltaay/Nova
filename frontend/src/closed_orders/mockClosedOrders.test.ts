import { describe, expect, it } from 'vitest';
import { formatOrderStatus } from '../ibkr/orderDisplay';
import { closedFillProgressAcceptable } from '../ibkr/orderQtyMath';
import {
  MOCK_CLOSED_IBKR_STATUSES,
  MOCK_CLOSED_TIMES,
  buildMockClosedOrders,
} from './mockClosedOrders';

describe('buildMockClosedOrders', () => {
  it('uppercases symbol and includes filled + cancelled rows', () => {
    const rows = buildMockClosedOrders('sdot');
    expect(rows.some((r) => r.symbol === 'SDOT' && r.status === 'Filled')).toBe(true);
    expect(rows.some((r) => r.status === 'Cancelled')).toBe(true);
  });

  it('covers every terminal IBKR closed status (Filled/Cancelled/ApiCancelled/Inactive)', () => {
    const statuses = new Set(buildMockClosedOrders('XYZ').map((o) => o.status));
    for (const s of MOCK_CLOSED_IBKR_STATUSES) {
      expect(statuses.has(s)).toBe(true);
    }
  });

  it('maps each sample row to a known Closed UI label', () => {
    for (const row of buildMockClosedOrders('XYZ')) {
      const label = formatOrderStatus(row.status, row.filled_qty ?? 0, row.qty);
      expect([
        'Filled',
        'Cancelled',
        'Cancelled (partial fill)',
        'Failed',
      ]).toContain(label);
    }
  });

  it('uses fixed Time Placed for every sample row (rebuilds never crawl)', () => {
    const a = buildMockClosedOrders('DEMO');
    const b = buildMockClosedOrders('DEMO');
    for (const row of a) {
      const key = row.order_id as keyof typeof MOCK_CLOSED_TIMES;
      expect(row.submitted_at).toBe(MOCK_CLOSED_TIMES[key].submitted_at);
    }
    expect(a.map((r) => r.submitted_at)).toEqual(b.map((r) => r.submitted_at));
    expect(a.map((r) => r.updated_at)).toEqual(b.map((r) => r.updated_at));
  });

  it('includes a just-completed demo row for recent highlight preview', () => {
    const row = buildMockClosedOrders('DEMO').find((r) => r.order_id === 9008);
    expect(row?.status).toBe('Filled');
    expect(row?.submitted_at).toBe(MOCK_CLOSED_TIMES[9008].submitted_at);
    expect(row?.updated_at).toBeTruthy();
    // Activity stamp is frozen at module load — still "recent" in this test process.
    const age = Date.now() - Date.parse(row!.updated_at!);
    expect(age).toBeGreaterThanOrEqual(0);
    expect(age).toBeLessThan(60_000);
  });

  it('every row has acceptable closed fill progress', () => {
    for (const row of buildMockClosedOrders('PYRAMID')) {
      expect(closedFillProgressAcceptable(row)).toBe(true);
      expect(row.remaining_qty).toBe(0);
      expect((row.filled_qty ?? 0)).toBeLessThanOrEqual(row.qty);
    }
  });
});
