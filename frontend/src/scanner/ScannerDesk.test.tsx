/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  STOCK_VIEW_DOCK_SURFACE_KEY,
  STOCK_VIEW_MODULE_POSITIONS_TITLE,
  STOCK_VIEW_OPEN_ORDERS_COLLAPSED_KEY,
} from '../constants';
import type { IbkrPosition } from '../ibkr/types';
import { ScannerDesk } from './ScannerDesk';

const POSITION: IbkrPosition = {
  symbol: 'SMPL',
  qty: 200,
  market_price: 4.25,
  market_value: 850,
  avg_cost: 3.1,
  unrealized_pnl: 230,
  realized_pnl: 0,
};

const workspace = {
  selectedSymbol: 'SMPL',
  openStockView: vi.fn(),
  selectRowSymbol: vi.fn(),
};

vi.mock('../workspace/WorkspaceContext', () => ({
  useWorkspace: () => workspace,
}));

vi.mock('../ibkr/useIbkrStatus', () => ({
  useIbkrStatus: () => ({
    connected: true,
    mode: 'paper',
    spend_status: 'paper_armed',
  }),
}));

vi.mock('../ibkr/useIbkrAccount', () => ({
  useIbkrAccount: () => ({
    summary: { connected: true, mode: 'paper' },
    positions: [POSITION],
    orders: [],
    error: null,
    refresh: vi.fn(),
  }),
}));

vi.mock('../closed_orders/useClosedOrders', () => ({
  useClosedOrders: () => ({
    orders: [],
    loading: false,
    refresh: () => {},
  }),
}));

vi.mock('../stock_view/TraderNovaOsBrain', () => ({
  TraderNovaOsBrain: ({ symbol }: { symbol: string }) => (
    <div data-testid="trader-nova-os-brain">Nova OS mock {symbol}</div>
  ),
}));

describe('ScannerDesk', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    workspace.openStockView.mockReset();
    workspace.selectRowSymbol.mockReset();
    localStorage.removeItem(STOCK_VIEW_OPEN_ORDERS_COLLAPSED_KEY);
    localStorage.setItem(STOCK_VIEW_DOCK_SURFACE_KEY, 'positions');
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it('mounts the Trader account dock under scanner tables and shows positions', async () => {
    await act(async () => {
      root.render(
        <ScannerDesk>
          <div data-testid="scanner-tables-slot">Gappers</div>
        </ScannerDesk>,
      );
    });

    expect(container.querySelector('[data-testid="scanner-desk"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="scanner-tables-slot"]')?.textContent).toBe(
      'Gappers',
    );
    const dock = container.querySelector('[data-testid="stock-view-open-orders-dock"]');
    expect(dock).toBeTruthy();
    expect(dock?.getAttribute('data-dock-host')).toBe('scanner');
    expect(dock?.getAttribute('data-dock-symbol')).toBe('SMPL');
    expect(
      container.querySelector('[data-testid="stock-view-dock-tab-positions"]')?.textContent,
    ).toContain(STOCK_VIEW_MODULE_POSITIONS_TITLE);
    expect(container.querySelector('[data-testid="stock-view-positions"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="positions-table"]')?.textContent).toContain(
      'SMPL',
    );
  });

  it('opens Trader from a position row', async () => {
    await act(async () => {
      root.render(
        <ScannerDesk>
          <div>tables</div>
        </ScannerDesk>,
      );
    });

    const row = container.querySelector('tr.selectable-row') as HTMLTableRowElement;
    expect(row).toBeTruthy();
    await act(async () => {
      row.click();
    });
    expect(workspace.selectRowSymbol).toHaveBeenCalledWith('SMPL');
    expect(workspace.openStockView).toHaveBeenCalledWith('SMPL');
  });
});
