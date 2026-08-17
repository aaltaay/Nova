/**
 * @vitest-environment jsdom
 *
 * Typing / Trader open stays in this window. Extract / double-click pops out.
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TRADER_TABS_STORAGE_KEY } from '../constants';
import { useWorkspace, WorkspaceProvider } from './WorkspaceContext';

vi.mock('../ibkr/useIbkrStatus', () => ({
  useIbkrStatus: () => ({
    enabled: true,
    connected: true,
    mode: 'paper',
    gateway_mode: 'paper',
    orders_enabled: false,
    spend_status: 'locked',
  }),
}));

type Api = ReturnType<typeof useWorkspace>;
let latest: Api | null = null;

function Probe() {
  latest = useWorkspace();
  return null;
}

describe('Trader open vs extract', () => {
  let container: HTMLDivElement;
  let root: Root;
  let opened: string[];

  beforeEach(() => {
    latest = null;
    opened = [];
    sessionStorage.removeItem(TRADER_TABS_STORAGE_KEY);
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        json: async () => ({ discovery_provider: 'ibkr', data_feed: 'sip' }),
      })),
    );
    vi.stubGlobal(
      'open',
      vi.fn((url: string) => {
        opened.push(String(url));
        return { focus: vi.fn(), opener: null } as unknown as Window;
      }),
    );
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    sessionStorage.removeItem(TRADER_TABS_STORAGE_KEY);
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  async function mount(): Promise<void> {
    act(() => {
      root.render(
        <WorkspaceProvider>
          <Probe />
        </WorkspaceProvider>,
      );
    });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
  }

  it('openStockView adds a tab here and does not open a window', async () => {
    await mount();
    await act(async () => {
      latest?.openStockView('SPY');
    });
    await act(async () => {
      latest?.openStockView('IPST');
    });
    expect(latest?.traderTabs).toEqual(['SPY', 'IPST']);
    expect(latest?.activeTraderSymbol).toBe('IPST');
    expect(opened).toEqual([]);
  });

  it('extractTraderTab opens a window and removes the tab here', async () => {
    await mount();
    await act(async () => {
      latest?.openStockView('SPY');
    });
    await act(async () => {
      latest?.openStockView('IPST');
    });
    await act(async () => {
      latest?.extractTraderTab('IPST');
      await Promise.resolve();
    });
    expect(opened.some((u) => /symbol=IPST/i.test(u))).toBe(true);
    expect(latest?.traderTabs).toEqual(['SPY']);
    expect(latest?.activeTraderSymbol).toBe('SPY');
  });

  it('acceptTraderTabDrop adds a foreign tab and ignores a self drag', async () => {
    await mount();
    await act(async () => {
      latest?.openStockView('SPY');
    });
    await act(async () => {
      latest?.acceptTraderTabDrop({
        v: 1,
        symbol: 'IPST',
        sourceWindowId: 'other-window',
      });
    });
    expect(latest?.traderTabs).toEqual(['SPY', 'IPST']);
    const selfId = latest?.traderWindowId ?? '';
    await act(async () => {
      latest?.acceptTraderTabDrop({
        v: 1,
        symbol: 'QQQ',
        sourceWindowId: selfId,
      });
    });
    expect(latest?.traderTabs).toEqual(['SPY', 'IPST']);
  });

  it('showScannerView keeps tabs so Trader can return without a new subscribe', async () => {
    await mount();
    await act(async () => {
      latest?.openStockView('IPST');
    });
    expect(latest?.traderViewActive).toBe(true);
    await act(async () => {
      latest?.showScannerView();
    });
    expect(latest?.traderTabs).toEqual(['IPST']);
    expect(latest?.traderViewActive).toBe(false);
    await act(async () => {
      latest?.openStockView('IPST');
    });
    expect(latest?.traderTabs).toEqual(['IPST']);
    expect(latest?.traderViewActive).toBe(true);
  });
});
