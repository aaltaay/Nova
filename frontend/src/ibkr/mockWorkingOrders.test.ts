import { describe, expect, it } from 'vitest';
import {
  MOCK_WORKING_IBKR_STATUSES,
  MOCK_WORKING_SUBMITTED,
  buildMockWorkingOrders,
} from './mockWorkingOrders';
import { formatOrderStatus, orderSubmittedIso } from './orderDisplay';
import { fillProgressCoherent } from './orderQtyMath';

describe('mockWorkingOrders', () => {
  it('uses fixed submitted timestamps (not Date.now-relative)', () => {
    const a = buildMockWorkingOrders('DEMO');
    const b = buildMockWorkingOrders('DEMO');
    for (const row of a) {
      const key = row.order_id as keyof typeof MOCK_WORKING_SUBMITTED;
      expect(row.submitted_at).toBe(MOCK_WORKING_SUBMITTED[key]);
      expect(orderSubmittedIso(row)).toBe(row.submitted_at);
    }
    expect(a.map((r) => r.submitted_at)).toEqual(b.map((r) => r.submitted_at));
  });

  it('covers every open IBKR status we map (Submitted/PendingSubmit/PreSubmitted/ApiPending)', () => {
    const statuses = new Set(buildMockWorkingOrders('XYZ').map((o) => o.status));
    for (const s of MOCK_WORKING_IBKR_STATUSES) {
      expect(statuses.has(s)).toBe(true);
    }
  });

  it('maps each sample row to a known UI status label', () => {
    for (const row of buildMockWorkingOrders('XYZ')) {
      const label = formatOrderStatus(row.status, row.filled_qty ?? 0, row.qty);
      expect([
        'Working',
        'Pending',
        'Partially filled',
      ]).toContain(label);
      expect(fillProgressCoherent(row)).toBe(true);
    }
  });

  it('keeps filled / remaining / prices coherent on partials', () => {
    const partial = buildMockWorkingOrders('XYZ').find((o) => o.order_id === 90002)!;
    expect(partial.filled_qty).toBe(20);
    expect(partial.remaining_qty).toBe(30);
    expect(partial.qty).toBe(50);
    expect(partial.limit_price).toBe(24.25);
    expect(partial.avg_fill_price).toBe(24.24);
    expect(partial.stop_price).toBeNull();
  });

  it('anchored to a $4.25 sample symbol, the ladder sits next to its price (QA W31)', () => {
    const rows = buildMockWorkingOrders('SMPL', 4.25);
    const first = rows.find((o) => o.order_id === 90001)!;
    const stop = rows.find((o) => o.order_id === 90003)!;
    expect(first.limit_price).toBe(4.25);
    expect(stop.stop_price).toBeCloseTo(4.14, 2);
    for (const row of rows) {
      for (const px of [row.limit_price, row.stop_price, row.avg_fill_price]) {
        if (px != null) expect(px).toBeLessThan(5);
      }
    }
    // Unanchored rows keep the written prices.
    expect(buildMockWorkingOrders('SMPL')[0].limit_price).toBe(24.1);
  });

  it('stop sample exposes stop_price and null limit', () => {
    const stop = buildMockWorkingOrders('XYZ').find((o) => o.order_id === 90003)!;
    expect(stop.order_type).toBe('STP');
    expect(stop.stop_price).toBe(23.5);
    expect(stop.limit_price).toBeNull();
  });
});
