/**
 * @vitest-environment jsdom
 *
 * Serious contract tests for Open Orders numeric / time columns.
 * These must not regress: filled, remaining, limit, stop, avg fill, order id, time.
 */
import { describe, expect, it } from 'vitest';
import { createRoot } from 'react-dom/client';
import { act } from 'react';
import {
  formatOrderDateTime,
  formatOrderStatus,
  orderSideClass,
  orderStatusTone,
  orderSubmittedIso,
} from './orderDisplay';
import type { IbkrOrder } from './types';
import { renderWorkingOrderCell } from './workingOrderCells';
import { DEFAULT_WORKING_ORDER_COLUMNS } from './orderTableColumns';

const PARTIAL: IbkrOrder = {
  order_id: 424242,
  symbol: 'AAPL',
  side: 'BUY',
  qty: 100,
  filled_qty: 35,
  remaining_qty: 65,
  order_type: 'LMT',
  limit_price: 190.55,
  stop_price: null,
  avg_fill_price: 190.42,
  outside_rth: false,
  status: 'Submitted',
  submitted_at: '2026-07-18T13:41:23.000Z',
  // Deliberately later — Open Orders Time must ignore this.
  updated_at: '2026-07-18T18:00:00.000Z',
};

const STOP: IbkrOrder = {
  order_id: 7,
  symbol: 'TSLA',
  side: 'SELL',
  qty: 50,
  filled_qty: 0,
  remaining_qty: 50,
  order_type: 'STP',
  limit_price: null,
  stop_price: 220.1,
  avg_fill_price: null,
  outside_rth: true,
  status: 'Submitted',
  submitted_at: '2026-07-18T14:00:00.000Z',
  updated_at: '2026-07-18T14:00:00.000Z',
};

function renderCell(col: (typeof DEFAULT_WORKING_ORDER_COLUMNS)[number], order: IbkrOrder) {
  const statusLabel = formatOrderStatus(order.status, order.filled_qty ?? 0, order.qty);
  const container = document.createElement('table');
  const tbody = document.createElement('tbody');
  const tr = document.createElement('tr');
  tbody.appendChild(tr);
  container.appendChild(tbody);
  document.body.appendChild(container);
  const root = createRoot(tr);
  const ctx = {
    statusLabel,
    tone: orderStatusTone(statusLabel),
    placedIso: orderSubmittedIso(order),
    sideCls: orderSideClass(order.side),
    sideLabel: order.side,
  };
  act(() => {
    root.render(<>{renderWorkingOrderCell(col, order, ctx)}</>);
  });
  const text = tr.textContent ?? '';
  const html = tr.innerHTML;
  act(() => {
    root.unmount();
  });
  container.remove();
  return { text, html };
}

describe('workingOrderCells — Open Orders column contract', () => {
  it('Quantity Filled shows filled shares (not total qty)', () => {
    const { text, html } = renderCell('filled', PARTIAL);
    expect(text).toBe('35');
    expect(text).not.toBe('100');
    expect(html).toContain('title="35 of 100 shares filled"');
  });

  it('Quantity shows fractional shares (not rounded to 0)', () => {
    const { text } = renderCell('qty', {
      ...PARTIAL,
      qty: 0.0642,
      filled_qty: 0,
      remaining_qty: 0.0642,
    });
    expect(text).toBe('0.0642');
  });

  it('Remaining shows unfilled shares', () => {
    const { text, html } = renderCell('remaining', PARTIAL);
    expect(text).toBe('65');
    expect(html).toContain('title="65 shares still working"');
  });

  it('Remaining derives qty − filled when remaining_qty is null', () => {
    const { text } = renderCell('remaining', {
      ...PARTIAL,
      qty: 100,
      filled_qty: 40,
      remaining_qty: null,
    });
    expect(text).toBe('60');
  });

  it('Limit price formats as dollars', () => {
    const { text } = renderCell('limit', PARTIAL);
    expect(text).toBe('$190.55');
  });

  it('Stop price formats as dollars for STP', () => {
    const { text } = renderCell('stop', STOP);
    expect(text).toBe('$220.10');
  });

  it('Stop price is em-dash when absent (limit order)', () => {
    const { text } = renderCell('stop', PARTIAL);
    expect(text).toBe('—');
  });

  it('Average fill formats as dollars', () => {
    const { text } = renderCell('avg_fill', PARTIAL);
    expect(text).toBe('$190.42');
  });

  it('Average fill is em-dash when none', () => {
    const { text } = renderCell('avg_fill', STOP);
    expect(text).toBe('—');
  });

  it('Order ID is exact numeric id', () => {
    const { text, html } = renderCell('order_id', PARTIAL);
    expect(text).toBe('424242');
    expect(html).toContain('ibkr-order-id');
  });

  it('Time is submitted snapshot — ignores updated_at', () => {
    const iso = orderSubmittedIso(PARTIAL);
    expect(iso).toBe(PARTIAL.submitted_at);
    expect(iso).not.toBe(PARTIAL.updated_at);

    const { text, html } = renderCell('time', PARTIAL);
    const expected = formatOrderDateTime(PARTIAL.submitted_at);
    expect(text).toBe(expected);
    expect(text).toMatch(/09:41:23/);
    expect(text).not.toMatch(/14:00:00/); // would be updated_at in ET
    expect(html).toContain(`datetime="${PARTIAL.submitted_at}"`);
  });

  it('Time stays identical when updated_at changes', () => {
    const before = orderSubmittedIso(PARTIAL);
    const after = orderSubmittedIso({
      ...PARTIAL,
      updated_at: new Date().toISOString(),
    });
    expect(after).toBe(before);
    expect(formatOrderDateTime(before)).toBe(formatOrderDateTime(after));
  });

  it('Limit is em-dash for market / stop without limit', () => {
    expect(renderCell('limit', STOP).text).toBe('—');
  });
});
