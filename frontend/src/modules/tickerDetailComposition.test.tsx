/**
 * @vitest-environment jsdom
 */
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TickerDetailContent } from '../components/TickerDetailContent';
import { WorkspaceProvider } from '../workspace/WorkspaceContext';
import { ModuleVisibilityProvider } from '../workspace/useModuleVisibility';
import { LayoutStoreProvider } from '../workspace/useLayoutStore';
import { makeDetail } from './quoteFixtures';

vi.mock('../ibkr/useIbkrStatus', () => ({
  useIbkrStatus: () => ({
    enabled: true,
    connected: false,
    mode: 'paper',
    orders_enabled: false,
    spend_status: 'locked',
  }),
}));

const chartPropsSpy = vi.fn();
vi.mock('../TickerChart', () => ({
  TickerChart: (props: { symbol: string; lastTrade?: { symbol?: string } }) => {
    chartPropsSpy(props);
    return <div data-testid="mock-chart" />;
  },
}));

vi.mock('../ibkr/DepthAndTape', () => ({
  DepthAndTape: () => <div data-testid="mock-depth" />,
}));

const here = dirname(fileURLToPath(import.meta.url));

describe('TickerDetailContent composition (Phase 3)', () => {
  it('is composition-only (imports panels, no inline cq-grid markup)', () => {
    const src = readFileSync(join(here, '../components/TickerDetailContent.tsx'), 'utf8');
    expect(src).toMatch(/QuoteHeaderPanel/);
    expect(src).toMatch(/NewsPanel/);
    expect(src).toMatch(/FundamentalsPanel/);
    expect(src).toMatch(/DataSourcesPanel/);
    expect(src).toMatch(/WatchlistStripPanel/);
    expect(src).toMatch(/DepthTapePanel/);
    expect(src).not.toMatch(/cq-grid-key/);
    expect(src).not.toMatch(/onToggleBlock/);
    expect(src).not.toMatch(/NewsHeadlineSection/);
  });

  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    chartPropsSpy.mockClear();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (String(url).includes('/api/config')) {
          return { ok: true, json: async () => ({ discovery_provider: 'ibkr', data_feed: 'sip' }) };
        }
        if (String(url).includes('blocklist')) {
          return { ok: true, json: async () => ({ symbols: [] }) };
        }
        return { ok: false, json: async () => ({}) };
      }),
    );
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.unstubAllGlobals();
  });

  it('columns layout mounts panels in order', async () => {
    await act(async () => {
      root.render(
        <WorkspaceProvider>
          <ModuleVisibilityProvider>
            <LayoutStoreProvider>
              <TickerDetailContent
                detail={makeDetail()}
                selectedSymbol="AAPL"
                layout="columns"
                showChart
              />
            </LayoutStoreProvider>
          </ModuleVisibilityProvider>
        </WorkspaceProvider>,
      );
    });
    const modules = [...container.querySelectorAll('[data-module]')].map(el =>
      el.getAttribute('data-module'),
    );
    expect(modules).toContain('watchlist-strip');
    expect(modules).toContain('news');
    expect(modules).toContain('quote-header');
    expect(modules).toContain('fundamentals');
    expect(modules).toContain('data-sources');
    expect(container.querySelector('.cq-symbol')?.textContent).toBe('AAPL');
    expect(container.querySelector('.cq-price')?.textContent).toBe('190.50');
  });

  it('binds chart to selectedSymbol and omits lastTrade when detail is stale', async () => {
    await act(async () => {
      root.render(
        <WorkspaceProvider>
          <ModuleVisibilityProvider>
            <LayoutStoreProvider>
              <TickerDetailContent
                detail={makeDetail({ symbol: 'NXTC' })}
                selectedSymbol="MVO"
                layout="stack"
                showChart
              />
            </LayoutStoreProvider>
          </ModuleVisibilityProvider>
        </WorkspaceProvider>,
      );
    });
    expect(chartPropsSpy).toHaveBeenCalled();
    const props = chartPropsSpy.mock.calls.at(-1)?.[0] as {
      symbol: string;
      lastTrade?: { symbol?: string };
    };
    expect(props.symbol).toBe('MVO');
    expect(props.lastTrade).toBeUndefined();
  });
});
