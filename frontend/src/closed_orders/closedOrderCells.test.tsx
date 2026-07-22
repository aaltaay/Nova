/**
 * @vitest-environment jsdom
 * Contract tests for Closed Orders qty / price / id / time columns.
 */
import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { describe, expect, it } from 'vitest';
import {
  formatOrderDateTime,
  formatOrderStatus,
  orderSideClass,
  orderStatusTone,
  orderSubmittedIso,
} from '../ibkr/orderDisplay';
import type { ClosedOrderColumnId } from '../ibkr/orderTableColumns';
import { renderClosedOrderCell } from './closedOrderCells';
import type { ClosedOrder } from './types';

const FILLED: ClosedOrder = {
  order_id: 501,
  symbol: 'AAPL',
  side: 'BUY',
  qty: 100,
  filled_qty: 100,
  remaining_qty: 0,
  order_type: 'LMT',
  limit_price: 12.5,
  stop_price: null,
  avg_fill_price: 12.48,
  outside_rth: false,
  status: 'Filled',
  submitted_at: '2026-07-18T13:00:00.000Z',
  updated_at: '2026-07-18T13:41:23.000Z',
};

const PARTIAL_CANCEL: ClosedOrder = {
  order_id: 502,
  symbol: 'MSFT',
  side: 'SELL',
  qty: 80,
  filled_qty: 35,
  remaining_qty: 0,
  order_type: 'LMT',
  limit_price: 400.1,
  avg_fill_price: 400.05,
  outside_rth: true,
  status: 'Cancelled',
  submitted_at: '2026-07-18T12:00:00.000Z',
  updated_at: '2026-07-18T12:30:00.000Z',
};

function renderCell(col: ClosedOrderColumnId, order: ClosedOrder) {
  const statusLabel = formatOrderStatus(
    order.status,
    order.filled_qty ?? 0,
    order.qty,
  );
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
    root.render(<>{renderClosedOrderCell(col, order, ctx)}</>);
  });
  const text = tr.textContent ?? '';
  const html = tr.innerHTML;
  act(() => {
    root.unmount();
  });
  container.remove();
  return { text, html };
}

describe('closedOrderCells — column contract', () => {
  it('Quantity Filled / Limit / Avg fill / Order ID', () => {
    const filled = renderCell('filled', FILLED);
    expect(filled.text).toBe('100');
    expect(filled.html).toContain('title="100 of 100 shares filled"');
    expect(renderCell('limit', FILLED).text).toBe('$12.50');
    expect(renderCell('avg_fill', FILLED).text).toBe('$12.48');
    expect(renderCell('order_id', FILLED).text).toBe('501');
    expect(renderCell('qty', FILLED).text).toBe('100');
  });

  it('Quantity shows fractional shares (not rounded to 0)', () => {
    const { text, html } = renderCell('qty', {
      ...FILLED,
      qty: 0.0642,
      filled_qty: 0.0642,
    });
    expect(text).toBe('0.0642');
    expect(renderCell('filled', {
      ...FILLED,
      qty: 0.0642,
      filled_qty: 0.0642,
    }).html).toContain('title="0.0642 of 0.0642 shares filled"');
    expect(html).not.toContain('>0<');
  });

  it('partial cancel keeps filled qty and avg fill', () => {
    const filled = renderCell('filled', PARTIAL_CANCEL);
    expect(filled.text).toBe('35');
    expect(filled.html).toContain('title="35 of 80 shares filled"');
    expect(renderCell('avg_fill', PARTIAL_CANCEL).text).toBe('$400.05');
    expect(renderCell('limit', PARTIAL_CANCEL).text).toBe('$400.10');
    expect(renderCell('order_id', PARTIAL_CANCEL).text).toBe('502');
  });

  it('Time Placed uses submitted_at, not last fill/cancel', () => {
    const { text, html } = renderCell('time', FILLED);
    expect(text).toBe(formatOrderDateTime(FILLED.submitted_at));
    expect(text).toMatch(/09:00:00/);
    expect(text).not.toMatch(/09:41:23/);
    expect(html).toContain(`datetime="${FILLED.submitted_at}"`);
  });

  it('Time Filled uses filled_at when the order filled', () => {
    const filledRow = { ...FILLED, filled_at: '2026-07-18T13:41:23.000Z' };
    const { text, html } = renderCell('filled_at', filledRow);
    expect(text).toBe(formatOrderDateTime(filledRow.filled_at));
    expect(text).toMatch(/09:41:23/);
    expect(html).toContain(`datetime="${filledRow.filled_at}"`);
  });

  it('Time Filled shows — when the order never filled', () => {
    const { text, html } = renderCell('filled_at', { ...PARTIAL_CANCEL, filled_at: null });
    expect(text).toBe('—');
    expect(html).not.toContain('datetime=');
  });
});
