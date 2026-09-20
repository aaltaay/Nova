/**
 * @vitest-environment jsdom
 *
 * #357 acceptance line 1: on ?view=sample the header shows the Nova Marketing
 * Sample Data account figures, with no backend.
 *
 * This renders the REAL GlobalAppBar. An earlier version of this file
 * reimplemented the header's chrome expression in a local helper and bound it
 * back with a regex over GlobalAppBar.tsx, which meant every behavioural
 * assertion passed against a copy. The only contexts stubbed here are the two
 * providers a browser-less desk cannot supply (workspace + account poller);
 * the chrome decision, the cluster and the money formatting are the shipped
 * code paths.
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { GlobalAppBar } from '../components/GlobalAppBar';
import type { IbkrAccountState } from '../ibkr/IbkrAccountContext';
import type { WorkspaceValue } from '../workspace/WorkspaceContext';
import { SAMPLE_IBKR_ACCOUNT_STATE } from './sampleAccount';

let workspace: WorkspaceValue;
let account: IbkrAccountState;

vi.mock('../workspace/WorkspaceContext', () => ({
  useWorkspace: () => workspace,
}));

vi.mock('../ibkr/IbkrAccountContext', () => ({
  useIbkrAccountContext: () => account,
}));

vi.mock('../closed_orders/useClosedOrders', () => ({
  useClosedOrders: () => ({ orders: [], loading: false, error: null, refresh: () => {} }),
}));

vi.mock('../bot/BotArmControls', () => ({
  BotArmControls: () => <div data-testid="bot-arm-controls-stub" />,
}));
vi.mock('../bot/BotSymbolMenu', () => ({
  BotSymbolMenuHost: () => <div data-testid="bot-symbol-menu-host-stub" />,
}));

vi.mock('../workspace/useModuleVisibility', () => ({
  useModuleVisibility: () => ({ visibility: { trading: true }, setVisible: () => {} }),
}));

/**
 * The sample desk as a marketing machine actually sees it: no Nova API, so
 * WorkspaceProvider (which sits above the sample gate) reports the Gateway
 * down. Only the fields GlobalAppBar and its children read are meaningful;
 * the cast keeps this fixture from drifting every time WorkspaceValue grows a
 * field the header never touches.
 */
function backendlessWorkspace(overrides: Partial<WorkspaceValue> = {}): WorkspaceValue {
  return {
    selectedSymbol: 'SMPL',
    setSelectedSymbol: () => {},
    ibkrConnected: false,
    ibkrTransportConnected: false,
    ibkrMode: 'disconnected',
    ibkrGatewayMode: null,
    ibkrAccountKind: null,
    ibkrIntentionalMode: null,
    ibkrDisconnectHint: null,
    openStockView: () => {},
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
    traderWindowId: 'sample-window',
    traderDeskRole: 'host',
    traderDockOffer: null,
    publishTraderTabOffer: () => {},
    publishTraderTabOfferEnd: () => {},
    closeTraderView: () => {},
    traderViewActive: false,
    showScannerView: () => {},
    ...overrides,
  } as unknown as WorkspaceValue;
}

describe('sample desk account chrome (real GlobalAppBar)', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    workspace = backendlessWorkspace();
    account = SAMPLE_IBKR_ACCOUNT_STATE;
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    window.history.replaceState({}, '', '/');
  });

  function renderAt(path: string) {
    window.history.replaceState({}, '', path);
    act(() => {
      root.render(<GlobalAppBar />);
    });
  }

  it('shows the sample account figures with the Gateway reported down', () => {
    renderAt('/?view=sample');

    expect(container.querySelector('[data-testid="global-bar-offline"]')).toBeNull();
    expect(container.querySelector('[data-testid="global-bar-cluster"]')).toBeTruthy();
    expect(
      container.querySelector('[data-testid="global-bar-account-trigger"]')?.textContent,
    ).toContain('+$230.00');
    expect(
      container.querySelector('.global-app-bar__metric--netliq')?.textContent,
    ).toContain('$100,000.00');
  });

  it('marks the sample Trader route the same way', () => {
    renderAt('/?view=sample&symbol=SMPL');

    expect(container.querySelector('[data-testid="global-bar-offline"]')).toBeNull();
    expect(
      container.querySelector('[data-testid="global-bar-account-trigger"]')?.textContent,
    ).toContain('+$230.00');
  });

  it('still says IBKR offline on a live route with the same Gateway down', () => {
    // The mutation guard: if the sample check were dropped from GlobalAppBar
    // the first case would fail; if it were widened to every route this one
    // would, and a real desk would stop reporting a dead Gateway.
    renderAt('/');

    const offline = container.querySelector('[data-testid="global-bar-offline"]');
    expect(offline).toBeTruthy();
    expect(container.textContent).toMatch(/IBKR offline/);
    expect(container.querySelector('[data-testid="global-bar-cluster"]')).toBeNull();
  });

  it('does not treat a near-miss URL as the sample desk', () => {
    for (const path of ['/?view=samples', '/?view=SAMPLE', '/?view=stock&symbol=SMPL']) {
      renderAt(path);
      expect(
        container.querySelector('[data-testid="global-bar-offline"]'),
        `expected an offline chip at ${path}`,
      ).toBeTruthy();
    }
  });
});
