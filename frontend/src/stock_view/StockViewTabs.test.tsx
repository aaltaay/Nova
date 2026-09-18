/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  resetGlobalBarSlotsForTests,
  setGlobalBarTraderSlot,
} from '../components/globalBarSlots';
import type { WorkspaceValue } from '../workspace/WorkspaceContext';
import { StockViewTabs } from './StockViewTabs';

let workspace: WorkspaceValue;

vi.mock('../workspace/WorkspaceContext', () => ({
  useWorkspace: () => workspace,
}));

vi.mock('../pages/StockViewPage', () => ({
  StockViewPage: ({
    symbol,
    chartActive,
  }: {
    symbol: string;
    chartActive?: boolean;
  }) => (
    <div
      data-testid={`stock-view-page-${symbol}`}
      data-chart-active={chartActive ? '1' : '0'}
    >
      {symbol}
    </div>
  ),
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
    openStockView: () => {},
    selectRowSymbol: () => {},
    traderTabs: ['AAPL', 'MSFT'],
    traderLiveTabs: ['AAPL', 'MSFT'],
    activeTraderSymbol: 'AAPL',
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
    closeTraderView: () => {},
    traderViewActive: true,
    showScannerView: () => {},
    ...overrides,
  };
}

describe('StockViewTabs tab-strip placement', () => {
  let container: HTMLDivElement;
  let headerSlot: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    resetGlobalBarSlotsForTests();
    workspace = baseWorkspace();
    container = document.createElement('div');
    headerSlot = document.createElement('div');
    headerSlot.dataset.testid = 'fake-header-slot';
    document.body.appendChild(headerSlot);
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    headerSlot.remove();
    resetGlobalBarSlotsForTests();
  });

  it('renders the strip inline when no header slot is mounted', () => {
    act(() => {
      root.render(<StockViewTabs detached={false} />);
    });
    const rootEl = container.querySelector('[data-testid="sv-tabs-root"]')!;
    expect(rootEl.querySelector('.sv-tab-strip')).toBeTruthy();
    expect(headerSlot.querySelector('.sv-tab-strip')).toBeNull();
    expect(container.querySelector('[data-testid="stock-view-page-AAPL"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="stock-view-page-MSFT"]')).toBeTruthy();
  });

  it('portals the strip into the GlobalAppBar slot and moves back when the slot goes away', async () => {
    act(() => {
      setGlobalBarTraderSlot(headerSlot);
    });
    act(() => {
      root.render(<StockViewTabs detached={false} />);
    });
    const rootEl = container.querySelector('[data-testid="sv-tabs-root"]')!;
    expect(headerSlot.querySelector('.sv-tab-strip')).toBeTruthy();
    expect(rootEl.querySelector('.sv-tab-strip')).toBeNull();
    // Both tabs live in the header now; panes stay in the Trader tree.
    expect(headerSlot.querySelector('[data-testid="sv-tab-AAPL"]')).toBeTruthy();
    expect(headerSlot.querySelector('[data-testid="sv-tab-MSFT"]')).toBeTruthy();
    expect(rootEl.querySelector('[data-testid="stock-view-page-AAPL"]')).toBeTruthy();

    await act(async () => {
      setGlobalBarTraderSlot(null);
      await Promise.resolve();
    });
    expect(headerSlot.querySelector('.sv-tab-strip')).toBeNull();
    expect(rootEl.querySelector('.sv-tab-strip')).toBeTruthy();
  });

  it('hides Pop out on a float desk and keeps Dock plus close', () => {
    workspace = baseWorkspace({
      traderDeskRole: 'float',
      traderTabs: ['F'],
      traderLiveTabs: ['F'],
      activeTraderSymbol: 'F',
    });
    act(() => {
      root.render(<StockViewTabs detached />);
    });
    expect(container.querySelector('[data-testid="sv-tab-extract-F"]')).toBeNull();
    expect(container.querySelector('[data-testid="sv-tab-dock-F"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="sv-tab-F"] .sv-tab__close')).toBeTruthy();
  });

  it('keeps the strip inline when Trader is hidden behind Scanner even if a slot exists', () => {
    workspace = baseWorkspace({ traderViewActive: false });
    act(() => {
      setGlobalBarTraderSlot(headerSlot);
    });
    act(() => {
      root.render(<StockViewTabs detached={false} />);
    });
    expect(headerSlot.querySelector('.sv-tab-strip')).toBeNull();
    expect(container.querySelector('.sv-tab-strip')).toBeTruthy();
  });

  it('pauses chart/tape/depth apply on live-but-hidden tabs', () => {
    act(() => {
      root.render(<StockViewTabs detached={false} />);
    });
    expect(
      container.querySelector('[data-testid="stock-view-page-AAPL"]')?.getAttribute('data-chart-active'),
    ).toBe('1');
    expect(
      container.querySelector('[data-testid="stock-view-page-MSFT"]')?.getAttribute('data-chart-active'),
    ).toBe('0');
  });

  it('does not mount a StockViewPage for a gray / suspended tab', () => {
    workspace = baseWorkspace({
      traderTabs: ['AAPL', 'MSFT', 'NVDA', 'F'],
      traderLiveTabs: ['MSFT', 'NVDA', 'F'],
      activeTraderSymbol: 'F',
    });
    act(() => {
      root.render(<StockViewTabs detached={false} />);
    });
    expect(container.querySelector('[data-testid="stock-view-page-AAPL"]')).toBeNull();
    expect(container.querySelector('[data-testid="sv-tab-pane-AAPL"]')?.getAttribute('data-suspended')).toBe('1');
    expect(container.querySelector('[data-testid="stock-view-page-F"]')).toBeTruthy();
  });
});
