/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  GLOBAL_BAR_EMERGENCY_KILL_LABEL,
  GLOBAL_BAR_EMERGENCY_KILL_OPS,
  GLOBAL_BAR_EMERGENCY_KILL_TITLE,
  TRADER_DEFAULT_SYMBOL,
  TRADER_DEFAULT_SYMBOLS,
} from '../constants';
import { GlobalAppBar } from './GlobalAppBar';
import type { IbkrAccountState } from '../ibkr/IbkrAccountContext';
import type { WorkspaceValue } from '../workspace/WorkspaceContext';

const closeTraderView = vi.fn();
const showScannerView = vi.fn();
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

vi.mock('../bot/BotArmControls', () => ({
  BotArmControls: () => <div data-testid="bot-arm-controls-stub" />,
}));
vi.mock('../bot/BotSymbolMenu', () => ({
  BotSymbolMenuHost: () => <div data-testid="bot-symbol-menu-host-stub" />,
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
    ibkrTransportConnected: true,
    ibkrMode: 'paper',
    ibkrGatewayMode: 'paper',
    ibkrAccountKind: 'paper',
    ibkrIntentionalMode: null,
    ibkrDisconnectHint: null,
    ibkrSecondFactorStale: false,
    ibkrSecondFactorAgeSec: null,
    ibkrSessionReason: 'ok',
    ibkrPortsDark: false,
    openStockView,
    selectRowSymbol: () => {},
    traderTabs: [],
    traderLiveTabs: [],
    activeTraderSymbol: null,
    traderBlockNotice: null,
    dismissTraderBlockNotice: () => {},
    activateTraderTab: () => {},
    closeTraderTab: () => {},
    renameTraderTab: () => {},
    addTraderDraftTab: () => {},
    extractTraderTab: () => {},
    acceptTraderTabDrop: () => false,
    requestDockTraderTab: () => {},
    traderWindowId: 'test-window',
    traderDeskRole: 'host',
    traderDockOffer: null,
    publishTraderTabOffer: () => {},
    publishTraderTabOfferEnd: () => {},
    closeTraderView,
    traderViewActive: false,
    showScannerView,
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
    showScannerView.mockReset();
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

  it('marks Trader active and returns to Scanner without closing tabs', () => {
    workspace = baseWorkspace({
      traderTabs: ['AAPL'],
      activeTraderSymbol: 'AAPL',
      traderViewActive: true,
    });
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
    expect(showScannerView).toHaveBeenCalled();
    expect(closeTraderView).not.toHaveBeenCalled();
  });

  it('reopens Trader from Scanner when tabs are already open', () => {
    workspace = baseWorkspace({
      traderTabs: ['AAPL'],
      activeTraderSymbol: 'AAPL',
      traderViewActive: false,
      selectedSymbol: 'AAPL',
    });
    renderBar();
    const scanner = container.querySelector(
      '[data-testid="global-bar-nav-scanner"]',
    ) as HTMLButtonElement;
    const trader = container.querySelector(
      '[data-testid="global-bar-nav-trader"]',
    ) as HTMLButtonElement;
    expect(scanner.getAttribute('aria-pressed')).toBe('true');
    expect(trader.getAttribute('aria-pressed')).toBe('false');
    act(() => {
      trader.click();
    });
    expect(openStockView).toHaveBeenCalledWith('AAPL');
  });

  it('opens Trader on the default index symbol when none is selected', () => {
    workspace = baseWorkspace({ selectedSymbol: null, traderTabs: [] });
    renderBar();
    const trader = container.querySelector(
      '[data-testid="global-bar-nav-trader"]',
    ) as HTMLButtonElement;
    expect(trader.disabled).toBe(false);
    act(() => {
      trader.click();
    });
    expect(openStockView).toHaveBeenCalledWith(TRADER_DEFAULT_SYMBOL);
  });

  it('lets the operator pick QQQ or IWM from Trader index defaults', () => {
    workspace = baseWorkspace({ selectedSymbol: null, traderTabs: [] });
    renderBar();
    const toggle = container.querySelector(
      '[data-testid="global-bar-nav-trader-defaults"]',
    ) as HTMLButtonElement;
    expect(toggle).toBeTruthy();
    act(() => {
      toggle.click();
    });
    const labels = TRADER_DEFAULT_SYMBOLS.map((sym) => {
      const btn = container.querySelector(
        `[data-testid="trader-default-${sym}"]`,
      ) as HTMLButtonElement;
      expect(btn?.textContent).toBe(sym);
      return btn;
    });
    act(() => {
      labels[1].click();
    });
    expect(openStockView).toHaveBeenCalledWith('QQQ');
  });

  it('shows Paper | Live capsule when the scanner cluster is absent', () => {
    renderBar();
    const capsule = container.querySelector('[data-testid="header-gateway-mode-capsule"]');
    expect(capsule).toBeTruthy();
    const segs = capsule!.querySelectorAll('.gw-mode-capsule__seg');
    expect(capsule!.classList.contains('is-paper')).toBe(true);
    expect(segs[0].textContent).toMatch(/Paper/i);
    expect(segs[1].textContent).toMatch(/Live/i);
    expect(segs[0].classList.contains('is-paper')).toBe(true);
  });

  const scannerProps = {
    mode: 'closed' as const,
    health: { status: 'ok', latency_ms: 1 },
    activeFeed: 'ibkr' as const,
    feedFellBack: false,
    secondsAgo: 1,
    historyDate: null,
    historyDates: [],
    onHistoryChange: () => {},
    onLookup: () => {},
  };

  it('keeps scanner controls + status in the single middle column (no spacer)', () => {
    act(() => {
      root.render(<GlobalAppBar scanner={scannerProps} />);
    });
    const center = container.querySelector('[data-testid="global-bar-center"]');
    expect(center).toBeTruthy();
    expect(center!.querySelector('[data-testid="global-bar-scanner"]')).toBeTruthy();
    expect(center!.querySelector('[data-testid="global-bar-status"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="global-bar-trader-slot"]')).toBeNull();
    expect(container.querySelector('.global-app-bar__spacer')).toBeNull();
    expect(container.textContent).toMatch(/Market Closed/);
  });

  it('offers the Trader tab-strip slot instead of scanner controls while Trader is showing', async () => {
    const { getGlobalBarTraderSlot, resetGlobalBarSlotsForTests } = await import('./globalBarSlots');
    resetGlobalBarSlotsForTests();
    workspace = baseWorkspace({
      traderTabs: ['AAPL'],
      activeTraderSymbol: 'AAPL',
      traderViewActive: true,
    });
    act(() => {
      root.render(<GlobalAppBar scanner={scannerProps} />);
    });
    const slot = container.querySelector('[data-testid="global-bar-trader-slot"]');
    expect(slot).toBeTruthy();
    expect(getGlobalBarTraderSlot()).toBe(slot);
    // Scanner-only controls leave; the status cluster stays so the clock/desk chips survive.
    expect(container.querySelector('[data-testid="global-bar-scanner"]')).toBeNull();
    expect(container.querySelector('[data-testid="global-bar-status"]')).toBeTruthy();
    act(() => {
      root.unmount();
    });
    expect(getGlobalBarTraderSlot()).toBeNull();
    root = createRoot(container);
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

  it('places bot controls on a second header row, not in the primary right cluster', () => {
    renderBar();
    const header = container.querySelector('[data-testid="global-app-bar"]');
    const primary = container.querySelector('[data-testid="global-bar-primary"]');
    const right = container.querySelector('.global-app-bar__right');
    const botRow = container.querySelector('[data-testid="global-bar-bot"]');
    const stub = container.querySelector('[data-testid="bot-arm-controls-stub"]');
    const menuHost = container.querySelector('[data-testid="bot-symbol-menu-host-stub"]');
    expect(header).toBeTruthy();
    expect(primary).toBeTruthy();
    expect(right).toBeTruthy();
    expect(botRow).toBeTruthy();
    expect(stub).toBeTruthy();
    expect(menuHost).toBeTruthy();
    expect(primary!.contains(right!)).toBe(true);
    expect(botRow!.contains(stub!)).toBe(true);
    expect(botRow!.contains(menuHost!)).toBe(true);
    expect(right!.contains(stub!)).toBe(false);
    expect(primary!.contains(stub!)).toBe(false);
    expect(right!.querySelector('[data-testid="global-bar-account"]')).toBeTruthy();
    expect(right!.querySelector('[data-testid="global-bar-trade-lock"]')).toBeTruthy();
    const kids = Array.from(header!.children);
    expect(kids.indexOf(primary as Element)).toBeLessThan(kids.indexOf(botRow as Element));
  });

  it('places Cash vs Margin between the trade lock and Account', () => {
    account = baseAccount({
      summary: {
        connected: true,
        mode: 'paper',
        AccountType: 'CASH',
        NetLiquidation: 1000,
      },
    });
    renderBar();
    const right = container.querySelector('.global-app-bar__right');
    expect(right).toBeTruthy();
    const lock = right!.querySelector('[data-testid="global-bar-trade-lock"]');
    const type = right!.querySelector('[data-testid="global-bar-account-type"]');
    const accountBtn = right!.querySelector('[data-testid="global-bar-account-nav"]');
    expect(lock).toBeTruthy();
    expect(type).toBeTruthy();
    expect(accountBtn).toBeTruthy();
    expect(type!.textContent).toBe('Cash');
    const kids = Array.from(right!.children);
    expect(kids.indexOf(lock as Element)).toBeLessThan(kids.indexOf(type as Element));
    expect(kids.indexOf(type as Element)).toBeLessThan(kids.indexOf(accountBtn as Element));
  });

  it('shows Cash with raw AccountType when IBKR reports INDIVIDUAL and BP≈cash', () => {
    account = baseAccount({
      summary: {
        connected: true,
        mode: 'live',
        AccountType: 'INDIVIDUAL',
        TradingType: 'STKNOPT',
        BuyingPower: 376,
        TotalCashValue: 383,
        NetLiquidation: 540,
      },
    });
    renderBar();
    const type = container.querySelector(
      '[data-testid="global-bar-account-type"]',
    ) as HTMLElement;
    expect(type).toBeTruthy();
    expect(type.textContent).toBe('Cash');
    expect(type.getAttribute('data-kind')).toBe('cash');
    expect(type.getAttribute('title') ?? '').toContain('IBKR AccountType: INDIVIDUAL');
    expect(type.getAttribute('title') ?? '').toContain('IBKR TradingType-S: STKNOPT');
    expect(type.getAttribute('title') ?? '').not.toMatch(/\bMargin\b/);
  });

  it('hides the account-type chip when IBKR is disconnected', () => {
    workspace = baseWorkspace({ ibkrConnected: false, ibkrMode: 'disconnected' });
    account = baseAccount({ summary: null, orders: [] });
    renderBar();
    expect(container.querySelector('[data-testid="global-bar-account-type"]')).toBeNull();
  });

  it('places Emergency KILL immediately after Look Up with the four-op hover', () => {
    act(() => {
      root.render(<GlobalAppBar scanner={scannerProps} />);
    });
    const cluster = container.querySelector('[data-testid="global-bar-scanner"]') as HTMLElement;
    expect(cluster).toBeTruthy();
    const search = cluster.querySelector('.header-symbol-search') as HTMLElement;
    const lookUp = search?.querySelector('.side-search-btn') as HTMLButtonElement;
    const kill = cluster.querySelector(
      '[data-testid="global-bar-emergency-kill"]',
    ) as HTMLButtonElement;
    expect(lookUp?.textContent).toBe('Look Up');
    expect(kill).toBeTruthy();
    expect(kill.textContent).toBe(GLOBAL_BAR_EMERGENCY_KILL_LABEL);
    expect(kill.title).toBe(GLOBAL_BAR_EMERGENCY_KILL_TITLE);
    for (const op of GLOBAL_BAR_EMERGENCY_KILL_OPS) {
      expect(kill.title).toContain(op);
    }
    const kids = Array.from(cluster.children);
    expect(kids.indexOf(kill)).toBe(kids.indexOf(search) + 1);
  });

  it('keeps Emergency KILL in the header when Trader hides Look Up', () => {
    workspace = baseWorkspace({
      traderTabs: ['AAPL'],
      activeTraderSymbol: 'AAPL',
      traderViewActive: true,
    });
    act(() => {
      root.render(<GlobalAppBar scanner={scannerProps} />);
    });
    expect(container.querySelector('[data-testid="global-bar-scanner"]')).toBeNull();
    const center = container.querySelector('[data-testid="global-bar-center"]') as HTMLElement;
    const slot = center.querySelector('[data-testid="global-bar-trader-slot"]') as HTMLElement;
    const kill = center.querySelector(
      '[data-testid="global-bar-emergency-kill"]',
    ) as HTMLButtonElement;
    expect(slot).toBeTruthy();
    expect(kill).toBeTruthy();
    const kids = Array.from(center.children);
    expect(kids.indexOf(kill)).toBe(kids.indexOf(slot) + 1);
  });
});
