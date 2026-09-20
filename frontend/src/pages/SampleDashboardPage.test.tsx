/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { HodMomoFixtureProvider } from '../hod_momo/HodMomoFixtureProvider';
import { IbkrAccountProvider } from '../ibkr/IbkrAccountContext';
import { SampleDataProvider } from '../sample_data/SampleDataContext';
import { LayoutStoreProvider } from '../workspace/useLayoutStore';
import { ModuleVisibilityProvider } from '../workspace/useModuleVisibility';
import { SampleDashboardPage } from './SampleDashboardPage';

vi.mock('../workspace/WorkspaceContext', () => ({
  useWorkspace: () => ({
    selectedSymbol: null,
    setSelectedSymbol: vi.fn(),
    discoveryProvider: 'ibkr',
    setDiscoveryProvider: vi.fn(),
    alpacaFeed: 'iex',
    setAlpacaFeed: vi.fn(),
    ibkrConnected: true,
    ibkrMode: 'paper',
    ibkrGatewayMode: 'paper',
    ibkrAccountKind: 'paper',
    ibkrIntentionalMode: null,
    openStockView: vi.fn(),
    selectRowSymbol: vi.fn(),
    traderTabs: [],
    traderLiveTabs: [],
    activeTraderSymbol: null,
    traderBlockNotice: null,
    dismissTraderBlockNotice: vi.fn(),
    activateTraderTab: vi.fn(),
    closeTraderTab: vi.fn(),
    renameTraderTab: vi.fn(),
    addTraderDraftTab: vi.fn(),
    extractTraderTab: vi.fn(),
    closeTraderView: vi.fn(),
    traderViewActive: false,
    showScannerView: vi.fn(),
  }),
}));


describe('SampleDashboardPage', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    Element.prototype.scrollTo = vi.fn();
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

  it('renders populated gappers without live fetch and owns no marking strip', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    await act(async () => {
      root.render(
        <ModuleVisibilityProvider>
          <LayoutStoreProvider>
            <SampleDataProvider>
              <IbkrAccountProvider>
              <HodMomoFixtureProvider>
                <SampleDashboardPage onOpenTrader={() => {}} />
              </HodMomoFixtureProvider>
              </IbkrAccountProvider>
            </SampleDataProvider>
          </LayoutStoreProvider>
        </ModuleVisibilityProvider>,
      );
    });

    expect(container.querySelector('[data-testid="sample-dashboard"]')).toBeTruthy();
    // #357: the marking strip moved to SampleShell so the sample Trader route
    // carries it too. Ownership provably left this page rather than vanishing.
    expect(container.querySelector('[data-testid="sample-data-banner"]')).toBeNull();
    expect(container.querySelector('[data-testid="sample-data-badge"]')).toBeNull();
    expect(container.textContent).toMatch(/SMPL|GAPX|MOMO/);
    // Sample shell must not hit scanner/decide/HOD APIs for table data.
    const urls = fetchSpy.mock.calls.map((c) => String(c[0]));
    expect(urls.some((u) => u.includes('/gappers') || u.includes('/movers'))).toBe(false);
    fetchSpy.mockRestore();
  });

  it('shows shared News and Earnings columns on the Large Cap sample table', async () => {
    await act(async () => {
      root.render(
        <ModuleVisibilityProvider>
          <LayoutStoreProvider>
            <SampleDataProvider>
              <IbkrAccountProvider>
              <HodMomoFixtureProvider>
                <SampleDashboardPage onOpenTrader={() => {}} />
              </HodMomoFixtureProvider>
              </IbkrAccountProvider>
            </SampleDataProvider>
          </LayoutStoreProvider>
        </ModuleVisibilityProvider>,
      );
    });

    await act(async () => {
      (container.querySelector('[data-testid="scanner-nav-large_cap"]') as HTMLButtonElement).click();
    });

    const headers = [...container.querySelectorAll('thead th')].map(
      th => th.textContent?.replace(/[↑↓↕]/g, '').trim() ?? '',
    );
    expect(headers).toContain('News');
    expect(headers).toContain('Earnings');
    expect(headers).toContain('Days');
    expect(container.textContent).toMatch(/GOOGL|NVDA|ORCL/);
    expect(container.querySelector('.news-flame')).not.toBeNull();
    expect(container.querySelector('.earnings-dots')).not.toBeNull();
  });

  it('shows the shared Positions dock under the sample scanner tables', async () => {
    await act(async () => {
      root.render(
        <ModuleVisibilityProvider>
          <LayoutStoreProvider>
            <SampleDataProvider>
              <IbkrAccountProvider>
              <HodMomoFixtureProvider>
                <SampleDashboardPage onOpenTrader={() => {}} />
              </HodMomoFixtureProvider>
              </IbkrAccountProvider>
            </SampleDataProvider>
          </LayoutStoreProvider>
        </ModuleVisibilityProvider>,
      );
    });

    expect(container.querySelector('[data-testid="scanner-desk"]')).toBeTruthy();
    const positionsTab = container.querySelector(
      '[data-testid="stock-view-dock-tab-positions"]',
    ) as HTMLButtonElement;
    expect(positionsTab).toBeTruthy();
    await act(async () => {
      positionsTab.click();
    });
    expect(container.querySelector('[data-testid="stock-view-positions"]')?.textContent).toContain(
      'SMPL',
    );
  });
});

