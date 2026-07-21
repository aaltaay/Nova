/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
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
    openStockView: vi.fn(),
    stockViewSymbol: null,
    setStockViewSymbol: vi.fn(),
  }),
}));

describe('SampleDashboardPage', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
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

  it('renders sample banner and populated gappers without live fetch', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    await act(async () => {
      root.render(
        <ModuleVisibilityProvider>
          <LayoutStoreProvider>
            <SampleDataProvider>
              <SampleDashboardPage onOpenTrader={() => {}} onLeaveSample={() => {}} />
            </SampleDataProvider>
          </LayoutStoreProvider>
        </ModuleVisibilityProvider>,
      );
    });

    expect(container.querySelector('[data-testid="sample-dashboard"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="sample-data-banner"]')).toBeTruthy();
    expect(container.textContent).toMatch(/SMPL|GAPX|MOMO/);
    // Sample shell must not hit scanner/decide/HOD APIs for table data.
    const urls = fetchSpy.mock.calls.map((c) => String(c[0]));
    expect(urls.some((u) => u.includes('/gappers') || u.includes('/movers'))).toBe(false);
    fetchSpy.mockRestore();
  });
});
