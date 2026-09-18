import { describe, expect, it } from 'vitest';
import {
  formatExtendedHours,
  formatOrderDateTime,
  formatOrderSide,
  formatOrderStatus,
  formatOrderType,
  orderActivityIso,
  orderSideClass,
  orderSideRowClass,
  orderStatusTone,
  orderSubmittedIso,
  positionSideClass,
  positionSideRowClass,
} from './orderDisplay';

describe('orderDisplay', () => {
  it('maps sides to labels and color classes (tables use color, not Side column)', () => {
    expect(formatOrderSide('BUY')).toBe('Buy');
    expect(formatOrderSide('SELL')).toBe('Sell');
    expect(orderSideClass('BUY')).toBe('ibkr-side--buy');
    expect(orderSideClass('SELL')).toBe('ibkr-side--sell');
    expect(orderSideRowClass('BUY')).toBe('ibkr-order-row--buy');
    expect(orderSideRowClass('SELL')).toBe('ibkr-order-row--sell');
    expect(positionSideClass(100)).toBe('ibkr-side--buy');
    expect(positionSideClass(-40)).toBe('ibkr-side--sell');
    expect(positionSideRowClass(100)).toBe('ibkr-order-row--buy');
    expect(positionSideRowClass(-40)).toBe('ibkr-order-row--sell');
    expect(formatOrderType('LMT')).toBe('Limit Order');
    expect(formatOrderType('MKT')).toBe('Market Order');
    expect(formatOrderType('STP')).toBe('Stop Order');
    expect(formatOrderType('STP LMT')).toBe('Stop Limit Order');
    expect(formatOrderType('TRAIL')).toBe('Trailing Stop Order');
  });

  it('maps IBKR statuses to Webull-clean labels', () => {
    expect(formatOrderStatus('PreSubmitted', 0, 100)).toBe('Pending');
    expect(formatOrderStatus('PendingSubmit', 0, 25)).toBe('Pending');
    expect(formatOrderStatus('ApiPending', 0, 10)).toBe('Pending');
    expect(formatOrderStatus('Submitted', 0, 100)).toBe('Working');
    expect(formatOrderStatus('Submitted', 20, 50)).toBe('Partially filled');
    expect(formatOrderStatus('PreSubmitted', 20, 50)).toBe('Partially filled');
    expect(formatOrderStatus('Filled', 100, 100)).toBe('Filled');
    expect(formatOrderStatus('Cancelled', 0, 100)).toBe('Cancelled');
    expect(formatOrderStatus('Canceled', 0, 100)).toBe('Cancelled'); // US spelling
    expect(formatOrderStatus('Cancelled', 35, 100)).toBe(
      'Cancelled (partial fill)',
    );
    expect(formatOrderStatus('ApiCancelled', 0, 20)).toBe('Cancelled');
    expect(formatOrderStatus('ApiCancelled', 10, 80)).toBe(
      'Cancelled (partial fill)',
    );
    expect(formatOrderStatus('Inactive', 0, 100)).toBe('Failed');
    expect(formatOrderStatus('Inactive', 5, 100)).toBe('Failed');
    expect(formatOrderStatus('OrderRejected', 0, 10)).toBe('Failed');
  });

  it('labels session and status tone', () => {
    expect(formatExtendedHours(true)).toBe('Extended hours');
    expect(formatExtendedHours(false)).toBe('Regular hours');
    expect(orderStatusTone('Working')).toBe('working');
    expect(orderStatusTone('Partially filled')).toBe('partial');
    expect(orderStatusTone('Cancelled (partial fill)')).toBe('partial');
  });

  it('gives an unmapped broker status its own tone, not pending (D-013)', () => {
    expect(orderStatusTone('Pending')).toBe('pending');
    // A new IB status string must not render as if the order were working.
    expect(orderStatusTone('SomeNewIbStatus')).toBe('unknown');
    expect(orderStatusTone('—')).toBe('unknown');
    expect(formatOrderStatus('SomeNewIbStatus', 0, 100)).toBe('SomeNewIbStatus');
  });

  it('formats exact Eastern times with seconds', () => {
    const label = formatOrderDateTime('2026-07-18T13:41:23+00:00');
    expect(label).toMatch(/Jul 18, 2026/);
    expect(label).toMatch(/09:41:23/);
    expect(label.endsWith(' ET')).toBe(true);
    expect(formatOrderDateTime(null)).toBe('—');
  });

  it('treats timezone-less ISO as UTC so Time Filled matches Time Placed zone', () => {
    const zulu = formatOrderDateTime('2026-09-18T15:02:48Z');
    const naive = formatOrderDateTime('2026-09-18T15:02:48');
    expect(zulu).toMatch(/11:02:48/);
    expect(naive).toBe(zulu);
    expect(naive).not.toMatch(/15:02:48/);
    expect(zulu.endsWith(' ET')).toBe(true);
  });

  it('109741 place and honest fill share the 11:02 ET hour', () => {
    const placed = formatOrderDateTime('2026-09-18T15:02:48.551Z');
    const filledHonest = formatOrderDateTime('2026-09-18T15:02:48Z');
    const filledSkew = formatOrderDateTime('2026-09-18T19:02:48Z');
    expect(placed).toMatch(/11:02:48/);
    expect(filledHonest).toMatch(/11:02:48/);
    expect(filledSkew).toMatch(/15:02:48/);
    expect(filledHonest).not.toMatch(/15:02:48/);
  });

  it('formats fractional seconds when ISO carries them (audit)', () => {
    const label = formatOrderDateTime('2026-07-18T13:41:23.456Z');
    expect(label).toMatch(/09:41:23/);
    expect(label).toMatch(/456/);
    expect(label.endsWith(' ET')).toBe(true);
  });

  it('Open Orders time uses submitted_at only (never updated_at)', () => {
    const order = {
      submitted_at: '2026-07-18T13:41:23.000Z',
      updated_at: '2026-07-18T18:00:00.000Z',
    };
    expect(orderSubmittedIso(order)).toBe('2026-07-18T13:41:23.000Z');
    expect(orderActivityIso(order)).toBe('2026-07-18T18:00:00.000Z');
    expect(orderSubmittedIso({ submitted_at: null, updated_at: '2026-07-18T18:00:00.000Z' })).toBe(
      null,
    );
  });
});
