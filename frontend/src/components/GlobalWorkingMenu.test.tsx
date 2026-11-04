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

const desk = vi.hoisted(() => ({ venue: 'paper' as string | null }));

vi.mock('../ibkr/confirmedDeskVenue', () => ({
  getConfirmedDeskVenueSnapshot: () => ({ venue: desk.venue, generation: null }),
}));

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
    desk.venue = 'paper';
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

  function renderMenu(workingCount = 1, symbols = ['AAPL']) {
    act(() => {
      root.render(
        <GlobalWorkingMenu
          workingOrders={
            workingCount
              ? symbols.map((symbol, index) => ({
                  order_id: index + 1,
                  symbol,
                  side: 'BUY',
                  qty: 10,
                  order_type: 'LMT',
                  limit_price: 1,
                  status: 'Submitted',
                }))
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
    expect(cancelAllOrdersForSymbol).toHaveBeenCalledWith('AAPL', undefined, 'paper');
    expect(onRefresh).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  async function cancelAll() {
    await act(async () => {
      (container.querySelector('[data-testid="global-working-cancel-all"]') as HTMLButtonElement).click();
      await Promise.resolve();
    });
    await vi.waitFor(() => expect(onClose).toHaveBeenCalled());
  }

  it('names the venue read before the confirm, even when the desk moves during it', async () => {
    confirmApp.mockImplementation(async () => {
      desk.venue = 'live'; // the desk moved while the confirm was open
      return true;
    });
    renderMenu(1);

    await cancelAll();

    expect(cancelAllOrdersForSymbol).toHaveBeenCalledWith('AAPL', undefined, 'paper');
  });

  it('says once that the cancels stopped, however many stocks answered it', async () => {
    const error = 'The desk moved from Paper to Live: the cancels stopped, none went to Live.';
    cancelAllOrdersForSymbol.mockResolvedValue({ ok: false, cancelled: [], failed: [], error });
    renderMenu(1, ['AAPL', 'MSFT']);

    await cancelAll();

    expect(alertApp).toHaveBeenCalledOnce();
    expect(alertApp).toHaveBeenCalledWith({ title: 'Cancel all did not finish', message: error });
    expect(onRefresh).toHaveBeenCalled();
  });

  it('a stock that failed still leaves the next one cancelled, and is shown', async () => {
    cancelAllOrdersForSymbol.mockResolvedValueOnce({
      ok: false,
      cancelled: [],
      failed: [{ order_id: 1, error: 'busy' }],
      error: '1 cancel(s) failed',
    });
    renderMenu(1, ['AAPL', 'MSFT']);

    await cancelAll();

    expect(cancelAllOrdersForSymbol).toHaveBeenCalledWith('MSFT', undefined, 'paper');
    expect(alertApp).toHaveBeenCalledWith(expect.objectContaining({ message: '1 cancel(s) failed' }));
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
