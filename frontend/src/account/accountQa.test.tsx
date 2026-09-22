/**
 * @vitest-environment jsdom
 *
 * Account page findings from the QA sweep of 2026-09-22: C11 (null lists),
 * C28 / V32 (price cell), C29 (rows sharing an order id), C46 (range label),
 * C47 (P&L % while loading).
 */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { ACCOUNT_PERF_ROW_REALIZED, ACCOUNT_PRICE_NONE } from '../constantGroups/account_page';
import type { IbkrOrder } from '../ibkr/types';
import { normalizePracticeHistory } from './accountHistoryResource';
import { positionsFromIbkr, positionsFromPractice } from './accountPositions';
import { paperHistoryFixture } from './accountFixtures';
import { PositionsOrdersPanel } from './PositionsOrdersPanel';
import { rangePnlPercent } from './PerformancePanel';

afterEach(cleanup);

const filled = (perm: number): IbkrOrder => ({
  order_id: 0, perm_id: perm, symbol: 'GRML', side: 'BUY', qty: 1, filled_qty: 1, order_type: 'MKT',
  limit_price: null, avg_fill_price: 8.8 + perm / 100, status: 'Filled', filled_at: `2026-09-21T21:0${perm}:00Z`,
});

describe('Orders (Today)', () => {
  it('keeps every row that shares order id 0 (C29)', () => {
    render(<PositionsOrdersPanel practice={false} positions={[]} working={[]} closed={[filled(1), filled(2), filled(3), filled(4)]} fills={[]} />);
    expect(screen.getByTestId('account-order-filter-filled').textContent).toContain('4');
    expect(screen.getAllByTestId('account-order-0')).toHaveLength(4);
  });

  it('shows no price for an unfilled market order, and never IB unset prices (V32 / C28)', () => {
    const mkt: IbkrOrder = { order_id: 3, symbol: 'GRML', side: 'BUY', qty: 1, order_type: 'MKT', limit_price: null, status: 'Cancelled', submitted_at: '2026-09-21T21:05:53Z' };
    const unset: IbkrOrder = {
      order_id: 4, symbol: 'GRML', side: 'BUY', qty: 1, order_type: 'MKT', status: 'Submitted',
      limit_price: 1.7976931348623157e308, stop_price: 1.7976931348623157e308, submitted_at: '2026-09-21T21:06:00Z',
    };
    render(<PositionsOrdersPanel practice={false} positions={[]} working={[unset]} closed={[mkt]} fills={[]} />);
    const cells = [screen.getByTestId('account-order-3'), screen.getByTestId('account-order-4')].map(
      (row) => row.querySelectorAll('td')[5].textContent,
    );
    expect(cells).toEqual([ACCOUNT_PRICE_NONE, ACCOUNT_PRICE_NONE]);
    expect(screen.getByTestId('account-orders-table').textContent).not.toMatch(/MKT\s*$|179,769|e\+308/);
  });
});

describe('null lists never crash the Account page (C11)', () => {
  it('positions: null reads as no positions', () => {
    expect(positionsFromPractice(null)).toEqual([]);
    expect(positionsFromIbkr(undefined)).toEqual([]);
    expect(positionsFromPractice([{ symbol: 'GRML', qty: 1, avg_cost: 8.8, mark: 9, unrealized: 0.2 }, null as never])).toHaveLength(1);
  });

  it('a history with null lists is shaped; one with no components is unreadable', () => {
    const history = { ...paperHistoryFixture(), daily: null, fills: null, equity: 'x', warnings: null };
    const out = normalizePracticeHistory(history);
    expect(out?.daily).toEqual([]);
    expect(out?.fills).toEqual([]);
    expect(out?.equity).toEqual([]);
    expect(out?.warnings).toEqual([]);
    expect(normalizePracticeHistory({ ...paperHistoryFixture(), components: null })).toBeNull();
    expect(normalizePracticeHistory(null)).toBeNull();
  });
});

describe('Performance', () => {
  it('P&L % waits for the account instead of reading -100.00% (C47)', () => {
    expect(rangePnlPercent(-0.53, null)).toBeNull();
    expect(rangePnlPercent(-0.53, 99_999.47)).toBeCloseTo(-0.00053, 6);
  });

  it('labels the realized row with its range; only ALL is since the reset (C46)', () => {
    expect(ACCOUNT_PERF_ROW_REALIZED('1D', 'Sep 18')).toBe('Net realized · 1D');
    expect(ACCOUNT_PERF_ROW_REALIZED('ALL', 'Sep 18')).toBe('Net realized since reset (Sep 18)');
    expect(ACCOUNT_PERF_ROW_REALIZED('ALL', null)).toBe('Net realized since the ledger opened');
  });
});
