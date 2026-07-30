/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { GlobalAppBar } from './GlobalAppBar';
import type { IbkrAccountState } from '../ibkr/IbkrAccountContext';
import type { WorkspaceValue } from '../workspace/WorkspaceContext';

const closeTraderView = vi.fn();
const openStockView = vi.fn();

let workspace: WorkspaceValue;
let account: IbkrAccountState;

vi.mock('../workspace/WorkspaceContext', () => ({
  useWorkspace: () => workspace,
}));

vi.mock('../ibkr/IbkrAccountContext', () => ({
  useIbkrAccountContext: () => account,
}));

vi.mock('../closed_orders/useClosedOrders', () => ({
  useClosedOrders: () => ({
    orders: [],
    loading: false,
    error: null,
    refresh: () => {},
  }),
}));

vi.mock('../workspace/useModuleVisibility', () => ({
  useModuleVisibility: () => ({
    visibility: { trading: true },
    setVisible: () => {},
  }),
}));

const { requestOpenTradingTab } = vi.hoisted(() => ({
  requestOpenTradingTab: vi.fn(),
}));
vi.mock('./openTradingTabNav', () => ({
  requestOpenTradingTab,
}));

function baseWorkspace(overrides: Partial<WorkspaceValue> = {}): WorkspaceValue {
  return {
    selectedSymbol: 'AAPL',
    setSelectedSymbol: () => {},
    discoveryProvider: 'ibkr',
    setDiscoveryProvider: () => {},
    alpacaFeed: 'iex',
    setAlpacaFeed: () => {},
    scannerPersistentAuthoritative: true,
    ibkrConnected: true,
    ibkrMode: 'paper',
    ibkrGatewayMode: 'paper',
    openStockView,
    traderTabs: [],
    activeTraderSymbol: null,
    traderBlockNotice: null,
    dismissTraderBlockNotice: () => {},
    activateTraderTab: () => {},
    closeTraderTab: () => {},
    renameTraderTab: () => {},
    addTraderDraftTab: () => {},
    closeTraderView,
    ...overrides,
  };
}

function baseAccount(overrides: Partial<IbkrAccountState> = {}): IbkrAccountState {
  return {
    summary: {
      connected: true,
      mode: 'paper',
      NetLiquidation: 3559.55,
      BuyingPower: 3558.53,
      UnrealizedPnL: -0.17,
      RealizedPnL: 0,
      TotalCashValue: 3558.53,
      GrossPositionValue: 1.02,
    },
    positions: [],
    orders: [],
    loading: false,
    error: null,
    refresh: () => {},
    ...overrides,
  };
}

describe('GlobalAppBar', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    closeTraderView.mockReset();
    openStockView.mockReset();
    requestOpenTradingTab.mockReset();
    workspace = baseWorkspace();
    account = baseAccount();
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

  function renderBar() {
    act(() => {
      root.render(<GlobalAppBar />);
    });
  }

  it('shows Day P&L, Net Liq, BP, Working when connected', () => {
    account = baseAccount({
      orders: [
        {
          order_id: 1,
          symbol: 'AAPL',
          side: 'BUY',
          qty: 10,
          order_type: 'LMT',
          limit_price: 1,
          status: 'Submitted',
        },
      ],
    });
    renderBar();
    const bar = container.querySelector('[data-testid="global-app-bar"]');
    expect(bar).toBeTruthy();
    expect(bar!.textContent).toMatch(/Day P&L/);
    expect(bar!.textContent).toMatch(/-\$0\.17/);
    expect(bar!.textContent).toMatch(/Net Liq/);
    expect(bar!.textContent).toMatch(/\$3,559\.55/);
    expect(bar!.textContent).toMatch(/BP/);
    expect(bar!.textContent).toMatch(/Working/);
    expect(bar!.textContent).toMatch(/1/);
    expect(container.querySelector('[data-testid="global-bar-offline"]')).toBeNull();
  });

  it('opens the Working special menu from the Working trigger', () => {
    renderBar();
    const trigger = container.querySelector(
      '[data-testid="global-bar-working-trigger"]',
    ) as HTMLButtonElement;
    act(() => {
      trigger.click();
    });
    const menu = container.querySelector('[data-testid="global-working-menu"]');
    expect(menu).toBeTruthy();
    expect(menu!.textContent).toMatch(/Cancel All \(Stocks\)/);
    expect(menu!.textContent).toMatch(/View All Orders/);
    expect(container.querySelector('[data-testid="global-bar-account-trigger"]')).toBeTruthy();
  });

  it('shows offline chip and placeholders when disconnected', () => {
    workspace = baseWorkspace({ ibkrConnected: false, ibkrMode: 'disconnected' });
    account = baseAccount({ summary: null, orders: [] });
    renderBar();
    expect(container.querySelector('[data-testid="global-bar-offline"]')).toBeTruthy();
    expect(container.textContent).toMatch(/IBKR offline/);
    expect(container.textContent).toMatch(/--/);
    expect(container.querySelector('[data-testid="global-bar-cluster"]')).toBeNull();
  });

  it('does not say IBKR offline when Gateway is up but account is still loading', () => {
    workspace = baseWorkspace({ ibkrConnected: true, ibkrMode: 'live' });
    account = baseAccount({ summary: null, orders: [], loading: true, error: null });
    renderBar();
    const chip = container.querySelector('[data-testid="global-bar-offline"]');
    expect(chip).toBeTruthy();
    expect(chip?.getAttribute('data-chrome')).toBe('loading');
    expect(container.textContent).toMatch(/Account…/);
    expect(container.textContent).not.toMatch(/IBKR offline/);
  });

  it('says Account unavailable (not offline) when Gateway is up but account poll failed', () => {
    workspace = baseWorkspace({ ibkrConnected: true, ibkrMode: 'live' });
    account = baseAccount({
      summary: null,
      orders: [],
      loading: false,
      error: 'account (HTTP 503)',
    });
    renderBar();
    const chip = container.querySelector('[data-testid="global-bar-offline"]');
    expect(chip?.getAttribute('data-chrome')).toBe('unavailable');
    expect(container.textContent).toMatch(/Account unavailable/);
    expect(container.textContent).not.toMatch(/IBKR offline/);
  });

  it('marks Scanner active and opens Trader from selected symbol', () => {
    renderBar();
    const scanner = container.querySelector(
      '[data-testid="global-bar-nav-scanner"]',
    ) as HTMLButtonElement;
    const trader = container.querySelector(
      '[data-testid="global-bar-nav-trader"]',
    ) as HTMLButtonElement;
    expect(scanner.getAttribute('aria-pressed')).toBe('true');
    expect(trader.disabled).toBe(false);
    act(() => {
      trader.click();
    });
    expect(openStockView).toHaveBeenCalledWith('AAPL');
  });

  it('marks Trader active and returns to Scanner via closeTraderView', () => {
    workspace = baseWorkspace({ traderTabs: ['AAPL'], activeTraderSymbol: 'AAPL' });
    renderBar();
    const scanner = container.querySelector(
      '[data-testid="global-bar-nav-scanner"]',
    ) as HTMLButtonElement;
    const trader = container.querySelector(
      '[data-testid="global-bar-nav-trader"]',
    ) as HTMLButtonElement;
    expect(trader.getAttribute('aria-pressed')).toBe('true');
    act(() => {
      scanner.click();
    });
    expect(closeTraderView).toHaveBeenCalled();
  });

  it('disables Trader when no symbol and no tabs', () => {
    workspace = baseWorkspace({ selectedSymbol: null, traderTabs: [] });
    renderBar();
    const trader = container.querySelector(
      '[data-testid="global-bar-nav-trader"]',
    ) as HTMLButtonElement;
    expect(trader.disabled).toBe(true);
  });

  it('places Account next to Settings and opens the trading tab', () => {
    renderBar();
    const accountBtn = container.querySelector(
      '[data-testid="global-bar-account-nav"]',
    ) as HTMLButtonElement;
    expect(accountBtn).toBeTruthy();
    expect(accountBtn.textContent).toMatch(/Account/);
    act(() => {
      accountBtn.click();
    });
    expect(requestOpenTradingTab).toHaveBeenCalled();
  });
});
