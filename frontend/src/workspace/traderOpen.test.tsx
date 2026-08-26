/**
 * @vitest-environment jsdom
 *
 * A ticker click (openStockView) opens Trader here and replaces the active
 * tab (ADR 011 decision 7) -- it never stacks a second tab. Only `+` /
 * dock / drop grow the strip. Extract / tab double-click pops out.
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

  it('openStockView opens the first symbol here, then replaces the active tab', async () => {
    await mount();
    await act(async () => {
      latest?.openStockView('SPY');
    });
    expect(latest?.traderTabs).toEqual(['SPY']);
    expect(latest?.activeTraderSymbol).toBe('SPY');
    await act(async () => {
      latest?.openStockView('IPST');
    });
    expect(latest?.traderTabs).toEqual(['IPST']);
    expect(latest?.activeTraderSymbol).toBe('IPST');
    expect(opened).toEqual([]);
  });

  it('openStockView activates an already-open symbol instead of duplicating it', async () => {
    await mount();
    await act(async () => {
      latest?.openStockView('SPY');
    });
    await act(async () => {
      latest?.acceptTraderTabDrop({ v: 1, symbol: 'IPST', sourceWindowId: 'other-window' });
    });
    expect(latest?.traderTabs).toEqual(['SPY', 'IPST']);
    await act(async () => {
      latest?.openStockView('spy');
    });
    expect(latest?.traderTabs).toEqual(['SPY', 'IPST']);
    expect(latest?.activeTraderSymbol).toBe('SPY');
  });

  it('extractTraderTab opens a window and removes the tab here', async () => {
    await mount();
    await act(async () => {
      latest?.openStockView('IPST');
    });
    await act(async () => {
      latest?.acceptTraderTabDrop({ v: 1, symbol: 'SPY', sourceWindowId: 'other-window' });
    });
    expect(latest?.traderTabs).toEqual(['IPST', 'SPY']);
    await act(async () => {
      latest?.extractTraderTab('SPY');
      await Promise.resolve();
    });
    expect(opened.some((u) => /symbol=SPY/i.test(u))).toBe(true);
    expect(latest?.traderTabs).toEqual(['IPST']);
    expect(latest?.activeTraderSymbol).toBe('IPST');
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

  it('selectRowSymbol on Scanner only updates selectedSymbol -- it does not open Trader', async () => {
    await mount();
    await act(async () => {
      latest?.selectRowSymbol('ipst');
    });
    expect(latest?.selectedSymbol).toBe('IPST');
    expect(latest?.traderTabs).toEqual([]);
    expect(latest?.traderViewActive).toBe(false);
  });

  it('selectRowSymbol while Trader is showing switches the active tab instead', async () => {
    await mount();
    await act(async () => {
      latest?.openStockView('SPY');
    });
    expect(latest?.traderTabs).toEqual(['SPY']);
    await act(async () => {
      latest?.selectRowSymbol('IPST');
    });
    expect(latest?.traderTabs).toEqual(['IPST']);
    expect(latest?.activeTraderSymbol).toBe('IPST');
    expect(latest?.selectedSymbol).toBe('IPST');
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
