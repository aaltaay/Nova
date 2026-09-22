/**
 * @vitest-environment jsdom
 *
 * A ticker click (openStockView) opens into the strip's preview tab -- the one
 * unpinned symbol -- replacing it, or activates a symbol already open. A pinned
 * tab stays; a docked tab arrives pinned beside the preview. Live L2 slots cap
 * at 3; extras stay on the strip grayed. Extract / tab double-click pops out.
 * Dock-back must restore the tab on the host. (ADR 011, amended 2026-09-22.)
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TRADER_TABS_STORAGE_KEY } from '../constants';
import {
  TRADER_DESK_STORAGE_KEY,
  encodeDeskStoragePayload,
  traderDeskMessage,
} from './traderDesk/protocol';
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
    window.history.replaceState({}, '', '/');
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
    window.history.replaceState({}, '', '/');
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

  /** Open by click, then pin -- how an operator keeps a tab on the strip. */
  async function openPinned(sym: string): Promise<void> {
    await act(async () => {
      latest?.openStockView(sym);
    });
    await act(async () => {
      latest?.pinTraderTab(sym);
    });
  }

  it('openStockView opens into the preview tab: a second click replaces an unpinned first', async () => {
    await mount();
    await act(async () => {
      latest?.openStockView('A');
    });
    expect(latest?.traderTabs).toEqual(['A']);
    expect(latest?.traderPinnedTabs).toEqual([]);
    await act(async () => {
      latest?.openStockView('B');
    });
    expect(latest?.traderTabs).toEqual(['B']);
    expect(latest?.activeTraderSymbol).toBe('B');
    expect(latest?.traderLiveTabs).toEqual(['B']);
    expect(opened).toEqual([]);
  });

  it('pinned tabs accumulate; the preview follows the newest click', async () => {
    await mount();
    await openPinned('A');
    await openPinned('B');
    await act(async () => {
      latest?.openStockView('C');
    });
    expect(latest?.traderTabs).toEqual(['A', 'B', 'C']);
    expect(latest?.traderPinnedTabs).toEqual(['A', 'B']);
    await act(async () => {
      latest?.openStockView('D');
    });
    expect(latest?.traderTabs).toEqual(['A', 'B', 'D']);
    expect(latest?.activeTraderSymbol).toBe('D');
    await act(async () => {
      latest?.unpinTraderTab('A');
    });
    expect(latest?.traderPinnedTabs).toEqual(['B']);
  });

  it('openStockView D keeps four pinned-then-preview tabs, lives D, and grays the least-recent live', async () => {
    await mount();
    for (const sym of ['A', 'B', 'C']) {
      await openPinned(sym);
    }
    await act(async () => {
      latest?.openStockView('D');
    });
    expect(latest?.traderTabs).toEqual(['A', 'B', 'C', 'D']);
    expect(latest?.activeTraderSymbol).toBe('D');
    expect(latest?.traderLiveTabs).toEqual(['B', 'C', 'D']);
  });

  it('activating a gray tab promotes it and suspends the oldest live tab', async () => {
    await mount();
    for (const sym of ['A', 'B', 'C', 'D']) {
      await openPinned(sym);
    }
    await act(async () => {
      latest?.activateTraderTab('A');
    });
    expect(latest?.activeTraderSymbol).toBe('A');
    expect(latest?.traderLiveTabs).toEqual(['C', 'D', 'A']);
    expect(latest?.traderTabs).toEqual(['A', 'B', 'C', 'D']);
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

  it('extractTraderTab is a no-op on an already popped-out window', async () => {
    window.history.replaceState({}, '', '/?view=stock&symbol=F');
    await mount();
    expect(latest?.traderDeskRole).toBe('float');
    expect(latest?.traderTabs).toEqual(['F']);
    await act(async () => {
      latest?.extractTraderTab('F');
      await Promise.resolve();
    });
    expect(opened).toEqual([]);
    expect(latest?.traderTabs).toEqual(['F']);
    window.history.replaceState({}, '', '/');
  });

  it('dock-request over the storage bus restores the ticker on the host desk, pinned', async () => {
    await mount();
    await act(async () => {
      latest?.openStockView('F');
    });
    await act(async () => {
      latest?.extractTraderTab('F');
      await Promise.resolve();
    });
    expect(latest?.traderTabs).toEqual([]);
    expect(latest?.traderViewActive).toBe(true);
    await act(async () => {
      window.dispatchEvent(new StorageEvent('storage', {
        key: TRADER_DESK_STORAGE_KEY,
        newValue: encodeDeskStoragePayload(traderDeskMessage('dock-request', {
          symbol: 'F',
          sourceWindowId: 'float-other',
          requestId: 'req-restore-f',
        })),
      }));
    });
    expect(latest?.traderTabs).toEqual(['F']);
    expect(latest?.traderPinnedTabs).toEqual(['F']);
    expect(latest?.activeTraderSymbol).toBe('F');
    expect(latest?.traderViewActive).toBe(true);
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

  it('acceptTraderTabDrop can add a 4th name instead of blocking', async () => {
    await mount();
    for (const sym of ['A', 'B', 'C']) {
      await openPinned(sym);
    }
    await act(async () => {
      latest?.acceptTraderTabDrop({ v: 1, symbol: 'D', sourceWindowId: 'float-other' });
    });
    expect(latest?.traderTabs).toEqual(['A', 'B', 'C', 'D']);
    expect(latest?.traderLiveTabs).toEqual(['B', 'C', 'D']);
  });

  it('acceptTraderTabDrop adds a foreign tab beside the preview, pinned, and ignores a self drag', async () => {
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
    expect(latest?.traderPinnedTabs).toEqual(['IPST']);
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

  it('selectRowSymbol while Trader is showing opens into the preview tab; a pinned tab is kept', async () => {
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
    await act(async () => {
      latest?.pinTraderTab('IPST');
    });
    await act(async () => {
      latest?.selectRowSymbol('QQQ');
    });
    expect(latest?.traderTabs).toEqual(['IPST', 'QQQ']);
  });

  it('a typed symbol arrives pinned, so the next click opens beside it', async () => {
    await mount();
    await act(async () => {
      latest?.addTraderDraftTab();
    });
    await act(async () => {
      latest?.renameTraderTab('', 'grml');
    });
    expect(latest?.traderTabs).toEqual(['GRML']);
    expect(latest?.traderPinnedTabs).toEqual(['GRML']);
    await act(async () => {
      latest?.openStockView('CCL');
    });
    expect(latest?.traderTabs).toEqual(['GRML', 'CCL']);
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
