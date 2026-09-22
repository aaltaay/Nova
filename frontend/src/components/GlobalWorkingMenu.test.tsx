/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { GlobalWorkingMenu } from './GlobalWorkingMenu';
import {
  consumeOpenTradingTabRequest,
  requestOpenTradingTab,
} from './openTradingTabNav';

const cancelAllOrdersForSymbol = vi.fn();
const confirmApp = vi.fn();
const alertApp = vi.fn();

vi.mock('../ibkr/placeOrder', () => ({
  cancelAllOrdersForSymbol: (...args: unknown[]) => cancelAllOrdersForSymbol(...args),
}));

vi.mock('../ux', () => ({
  confirmApp: (...args: unknown[]) => confirmApp(...args),
  alertApp: (...args: unknown[]) => alertApp(...args),
}));

describe('GlobalWorkingMenu', () => {
  let container: HTMLDivElement;
  let root: Root;
  const closeTraderView = vi.fn();
  const onRefresh = vi.fn();
  const onClose = vi.fn();

  beforeEach(() => {
    cancelAllOrdersForSymbol.mockReset().mockResolvedValue({
      ok: true,
      cancelled: [1],
      failed: [],
      error: null,
    });
    confirmApp.mockReset().mockResolvedValue(true);
    alertApp.mockReset().mockResolvedValue(undefined);
    closeTraderView.mockReset();
    onRefresh.mockReset();
    onClose.mockReset();
    // Drain any leftover latch from prior tests.
    consumeOpenTradingTabRequest();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    consumeOpenTradingTabRequest();
  });

  function renderMenu(workingCount = 1) {
    act(() => {
      root.render(
        <GlobalWorkingMenu
          workingOrders={
            workingCount
              ? [
                  {
                    order_id: 1,
                    symbol: 'AAPL',
                    side: 'BUY',
                    qty: 10,
                    order_type: 'LMT',
                    limit_price: 1,
                    status: 'Submitted',
                  },
                ]
              : []
          }
          closedOrders={[
            {
              order_id: 2,
              symbol: 'AAPL',
              side: 'BUY',
              qty: 5,
              order_type: 'MKT',
              limit_price: null,
              status: 'Filled',
              filled_qty: 5,
            },
          ]}
          traderActive={false}
          closeTraderView={closeTraderView}
          onRefresh={onRefresh}
          onClose={onClose}
        />,
      );
    });
  }

  it('renders Working / Filled / Canceled counts and action rows', () => {
    renderMenu(1);
    const menu = container.querySelector('[data-testid="global-working-menu"]');
    expect(menu?.textContent).toMatch(/Working Orders/);
    expect(menu?.textContent).toMatch(/Filled Today/);
    expect(menu?.textContent).toMatch(/Canceled & Failed/);
    expect(menu?.textContent).toMatch(/Cancel All \(Stocks\)/);
    expect(menu?.textContent).toMatch(/View All Orders/);
    // Equities-only desk: no options action is offered, disabled or not (V34).
    expect(menu?.textContent).not.toMatch(/Options/);
    expect(container.querySelector('[data-testid="global-working-cancel-options"]')).toBeNull();
  });

  it('cancels all stock symbols after confirm', async () => {
    renderMenu(1);
    await act(async () => {
      (container.querySelector('[data-testid="global-working-cancel-all"]') as HTMLButtonElement).click();
      await Promise.resolve();
    });
    expect(confirmApp).toHaveBeenCalled();
    expect(cancelAllOrdersForSymbol).toHaveBeenCalledWith('AAPL');
    expect(onRefresh).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it('View All Orders latches trading-tab request', () => {
    renderMenu(0);
    act(() => {
      (container.querySelector('[data-testid="global-working-view-all"]') as HTMLButtonElement).click();
    });
    expect(onClose).toHaveBeenCalled();
    expect(consumeOpenTradingTabRequest()).toBe(true);
    expect(consumeOpenTradingTabRequest()).toBe(false);
  });
});

describe('openTradingTabNav latch', () => {
  it('request then consume is one-shot', () => {
    consumeOpenTradingTabRequest();
    requestOpenTradingTab();
    expect(consumeOpenTradingTabRequest()).toBe(true);
    expect(consumeOpenTradingTabRequest()).toBe(false);
  });
});
