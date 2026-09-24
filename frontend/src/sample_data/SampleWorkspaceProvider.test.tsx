/**
 * @vitest-environment jsdom
 *
 * #449: the sample desk's own workspace. Its Trader tabs open, switch, preview
 * and pin in memory; it pops a tab out to a sample window; and it never
 * touches the live workspace it shadows or the operator's saved state.
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TRADER_EXTRACT_BLOCKED_MESSAGE } from '../constantGroups/trader_view';
import { useWorkspace, WorkspaceValueProvider, type WorkspaceValue } from '../workspace';
import { SAMPLE_POPOUT_DESKTOP_WHY, SAMPLE_TRADER_DOCK_WHY } from './sampleCopy';
import { SAMPLE_OWNED_WORKSPACE_KEYS, SampleWorkspaceProvider } from './SampleWorkspaceProvider';

/** The live workspace above the sample shell: every sample-owned field holds a value the sample must not show. */
function liveWorkspace(): WorkspaceValue {
  const fn = () => vi.fn();
  return {
    selectedSymbol: 'LIVE',
    setSelectedSymbol: fn(),
    discoveryProvider: 'ibkr',
    setDiscoveryProvider: fn(),
    alpacaFeed: 'iex',
    setAlpacaFeed: fn(),
    scannerPersistentAuthoritative: false,
    ibkrConnected: true,
    ibkrStatusKnown: true,
    ibkrStatusError: null,
    ibkrTransportConnected: true,
    ibkrSessionReason: null,
    ibkrPortsDark: false,
    ibkrDisconnectHint: null,
    ibkrSecondFactorStale: false,
    ibkrSecondFactorAgeSec: null,
    ibkrMode: 'paper',
    deskVenue: 'paper',
    ibkrGatewayMode: 'paper',
    ibkrAccountKind: null,
    ibkrIntentionalMode: null,
    openStockView: fn(),
    openTraderTab: fn(),
    selectRowSymbol: fn(),
    extractTraderTab: fn(),
    acceptTraderTabDrop: vi.fn(() => true),
    requestDockTraderTab: fn(),
    traderWindowId: 'live-window',
    traderDeskRole: 'float',
    traderDockOffer: { symbol: 'LIVE', sourceWindowId: 'other' },
    publishTraderTabOffer: fn(),
    publishTraderTabOfferEnd: fn(),
    traderTabs: ['LIVE'],
    traderLiveTabs: ['LIVE'],
    traderPinnedTabs: ['LIVE'],
    activeTraderSymbol: 'LIVE',
    traderBlockNotice: 'live notice',
    dismissTraderBlockNotice: fn(),
    activateTraderTab: fn(),
    closeTraderTab: fn(),
    pinTraderTab: fn(),
    unpinTraderTab: fn(),
    renameTraderTab: fn(),
    addTraderDraftTab: fn(),
    closeTraderView: fn(),
    traderViewActive: true,
    showScannerView: fn(),
    traderMoveLocks: null,
  };
}

let root: Root;
let container: HTMLDivElement;
let live: WorkspaceValue;
let ws: WorkspaceValue;
let writes: string[];

function Probe() {
  ws = useWorkspace();
  return null;
}

function mount(path: string): void {
  window.history.replaceState({}, '', path);
  live = liveWorkspace();
  act(() => {
    root.render(
      <WorkspaceValueProvider value={live}>
        <SampleWorkspaceProvider>
          <Probe />
        </SampleWorkspaceProvider>
      </WorkspaceValueProvider>,
    );
  });
}

beforeEach(() => {
  writes = [];
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation((key: string) => { writes.push(key); });
  vi.spyOn(Storage.prototype, 'removeItem').mockImplementation((key: string) => { writes.push(key); });
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.restoreAllMocks();
  delete (window as { novaDesktop?: unknown }).novaDesktop;
  window.history.replaceState({}, '', '/');
});

const liveCalls = () =>
  Object.values(live).filter((v): v is ReturnType<typeof vi.fn> => vi.isMockFunction(v) && v.mock.calls.length > 0);

describe('SampleWorkspaceProvider', () => {
  it('replaces every Trader field of the live workspace and keeps the rest', () => {
    mount('/?view=sample');
    for (const key of SAMPLE_OWNED_WORKSPACE_KEYS) {
      expect(ws[key], key).not.toBe(live[key]);
    }
    expect(ws.deskVenue).toBe('paper');
    expect(ws.ibkrConnected).toBe(true);
    expect(ws.traderTabs).toEqual([]);
    expect(ws.traderViewActive).toBe(false);
    expect(ws.traderDeskRole).toBe('host');
  });

  it('opens the URL symbol as the one tab, pinned, with the Trader up', () => {
    mount('/?view=sample&symbol=smpl');
    expect(ws.traderTabs).toEqual(['SMPL']);
    expect(ws.traderPinnedTabs).toEqual(['SMPL']);
    expect(ws.activeTraderSymbol).toBe('SMPL');
    expect(ws.selectedSymbol).toBe('SMPL');
    expect(ws.traderViewActive).toBe(true);
  });

  it('opens, previews, pins and switches tabs in memory -- nothing saved, nothing sent to the live desk', () => {
    mount('/?view=sample&symbol=SMPL');
    act(() => ws.openStockView('gapx'));
    expect(ws.traderTabs).toEqual(['SMPL', 'GAPX']);
    expect(ws.activeTraderSymbol).toBe('GAPX');
    // GAPX is the preview tab: the next open takes its place.
    act(() => ws.openStockView('NWSR'));
    expect(ws.traderTabs).toEqual(['SMPL', 'NWSR']);
    act(() => ws.pinTraderTab('NWSR'));
    act(() => ws.openStockView('CATZ'));
    expect(ws.traderTabs).toEqual(['SMPL', 'NWSR', 'CATZ']);
    act(() => ws.activateTraderTab('SMPL'));
    expect(ws.activeTraderSymbol).toBe('SMPL');
    expect(window.location.search).toBe('?view=sample&symbol=SMPL');
    act(() => ws.closeTraderTab('CATZ'));
    expect(ws.traderTabs).toEqual(['SMPL', 'NWSR']);
    act(() => ws.showScannerView());
    expect(ws.traderViewActive).toBe(false);
    expect(window.location.search).toBe('?view=sample');
    expect(writes).toEqual([]);
    expect(liveCalls()).toEqual([]);
  });

  it('a Desk open adds the tab beside the board without switching to the full Trader', () => {
    mount('/?view=sample');
    act(() => ws.openTraderTab('GAPX'));
    expect(ws.traderTabs).toEqual(['GAPX']);
    expect(ws.selectedSymbol).toBe('GAPX');
    expect(ws.traderViewActive).toBe(false);
  });

  it('pops a tab out to a sample window and closes it here', () => {
    const popup = { focus: vi.fn(), opener: window } as unknown as Window;
    const open = vi.spyOn(window, 'open').mockReturnValue(popup);
    mount('/?view=sample&symbol=SMPL');
    act(() => ws.openStockView('GAPX', { pin: true }));
    expect(ws.traderMoveLocks?.extract).toBeNull();
    act(() => ws.extractTraderTab('GAPX'));
    expect(open).toHaveBeenCalledTimes(1);
    const [url, name] = open.mock.calls[0];
    const target = new URL(String(url));
    expect(target.searchParams.get('view')).toBe('sample');
    expect(target.searchParams.get('symbol')).toBe('GAPX');
    expect(target.searchParams.get('popout')).toBe('1');
    expect(name).toBe('nova-sample-trader-GAPX');
    expect(popup.opener).toBeNull();
    expect(ws.traderTabs).toEqual(['SMPL']);
    expect(writes).toEqual([]);
  });

  it('a blocked pop-up says so and keeps the tab', () => {
    vi.spyOn(window, 'open').mockReturnValue(null);
    mount('/?view=sample&symbol=SMPL');
    act(() => ws.extractTraderTab('SMPL'));
    expect(ws.traderBlockNotice).toBe(TRADER_EXTRACT_BLOCKED_MESSAGE);
    expect(ws.traderTabs).toEqual(['SMPL']);
    act(() => ws.dismissTraderBlockNotice());
    expect(ws.traderBlockNotice).toBeNull();
  });

  it('in the desktop app pop-out is locked with its reason and opens nothing', () => {
    (window as { novaDesktop?: unknown }).novaDesktop = {};
    const open = vi.spyOn(window, 'open');
    mount('/?view=sample&symbol=SMPL');
    expect(ws.traderMoveLocks?.extract).toBe(SAMPLE_POPOUT_DESKTOP_WHY);
    act(() => ws.extractTraderTab('SMPL'));
    expect(open).not.toHaveBeenCalled();
    expect(ws.traderTabs).toEqual(['SMPL']);
  });

  it('a sample pop-out is a float with its one tab; it never docks, and closing its tab closes the window', () => {
    const close = vi.spyOn(window, 'close').mockImplementation(() => {});
    mount('/?view=sample&symbol=GAPX&popout=1');
    expect(ws.traderDeskRole).toBe('float');
    expect(ws.traderTabs).toEqual(['GAPX']);
    expect(ws.traderMoveLocks?.dock).toBe(SAMPLE_TRADER_DOCK_WHY);
    expect(ws.acceptTraderTabDrop({ symbol: 'LIVE', sourceWindowId: 'live-window' })).toBe(false);
    act(() => ws.requestDockTraderTab('GAPX'));
    expect(ws.traderTabs).toEqual(['GAPX']);
    act(() => ws.closeTraderTab('GAPX'));
    expect(close).toHaveBeenCalledTimes(1);
    expect(window.location.search).toBe('?view=sample&symbol=GAPX&popout=1');
    expect(writes).toEqual([]);
    expect(liveCalls()).toEqual([]);
  });
});
