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
} from '../constants';
import { GlobalAppBar } from './GlobalAppBar';
import type { IbkrAccountState } from '../ibkr/IbkrAccountContext';
import type { IbkrClientStatus } from '../ibkr/useIbkrStatus';
import { PAPER_ACCOUNT } from '../practice/practiceFixtures';
import type { PracticeAccount } from '../practice/practiceTypes';
import type { WorkspaceValue } from '../workspace/WorkspaceContext';

const closeTraderView = vi.fn();
const showScannerView = vi.fn();
const openStockView = vi.fn();

let workspace: WorkspaceValue;
let account: IbkrAccountState;

vi.mock('../workspace/WorkspaceContext', () => ({
  useWorkspace: () => workspace,
}));

// The account cluster reads /api/ibkr/status for the pill and polls Nova's
// practice ledger on Paper / Sim; both are held here so each test states what
// the desk is logged into (GlobalBarAccountCluster.test covers the cluster).
const { status, practice } = vi.hoisted(() => ({
  status: { current: {} as IbkrClientStatus },
  practice: { current: { data: null as PracticeAccount | null, error: null as string | null } },
}));
vi.mock('../ibkr/useIbkrStatus', () => ({
  useIbkrStatus: () => status.current,
}));
vi.mock('../practice/practiceAccountResource', () => ({
  usePracticeAccount: () => practice.current,
}));

function baseStatus(overrides: Partial<IbkrClientStatus> = {}): IbkrClientStatus {
  return {
    enabled: true,
    connected: true,
    transport_connected: true,
    session_reason: 'ok',
    mode: 'live',
    venue: 'live',
    orders_enabled: false,
    short_enabled: false,
    spend_status: 'locked',
    trading_allowed: false,
    trading_allowed_reason: null,
    market_data_type: 1,
    market_data_delayed: false,
    account_id: 'U1234567',
    account_ids: ['U1234567'],
    broker_account_kind: 'live',
    clientReady: true,
    stale: false,
    staleSince: null,
    ...overrides,
  };
}

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
    // Live: the header shows the IBKR account. Paper / Sim show Nova's ledger (ADR 020).
    ibkrMode: 'live',
    ibkrGatewayMode: 'live',
    ibkrAccountKind: 'live',
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
      mode: 'live',
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
    status.current = baseStatus();
    practice.current = { data: null, error: null };
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

  it("shows Day's, Working, TAV (no BP) on the one row when connected", () => {
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
    expect(bar!.textContent).toMatch(/Day's/);
    expect(bar!.textContent).toMatch(/-\$0\.17/);
    expect(bar!.textContent).toMatch(/TAV/);
    expect(bar!.textContent).toMatch(/\$3,559\.55/);
    // Slim header: BP is not a primary-row metric.
    expect(bar!.textContent).not.toMatch(/\bBP\b/);
    expect(bar!.textContent).not.toMatch(/\$3,558\.53/);
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

  it('shows Paper | Live capsule when the scanner cluster is absent', () => {
    workspace = baseWorkspace({ ibkrMode: 'paper', ibkrGatewayMode: 'paper', ibkrAccountKind: 'paper' });
    renderBar();
    const capsule = container.querySelector('[data-testid="header-gateway-mode-capsule"]');
    expect(capsule).toBeTruthy();
    const segs = capsule!.querySelectorAll('.gw-mode-capsule__seg');
    expect(capsule!.classList.contains('is-paper')).toBe(true);
    expect(segs[0].textContent).toMatch(/Paper/i);
    expect(segs[1].textContent).toMatch(/Live/i);
    expect(segs[2].textContent).toMatch(/Sim/i);
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

  it('ends the cluster with the account pill -- structure, class, full id -- before the trade lock', () => {
    account = baseAccount({
      summary: {
        connected: true,
        mode: 'live',
        AccountType: 'INDIVIDUAL',
        account_class: 'margin',
        NetLiquidation: 1000,
      },
    });
    renderBar();
    const right = container.querySelector('.global-app-bar__right') as HTMLElement;
    const wrap = right.querySelector('[data-testid="global-bar-account"]') as HTMLElement;
    const cluster = right.querySelector('[data-testid="global-bar-cluster"]') as HTMLElement;
    const lock = right.querySelector('[data-testid="global-bar-trade-lock"]') as HTMLElement;
    const pill = cluster.querySelector('[data-testid="global-bar-account-pill"]') as HTMLElement;
    expect(pill).toBeTruthy();
    expect(pill.textContent).toContain('Individual Margin (U1234567)');
    expect(pill.getAttribute('data-kind')).toBe('live');
    expect(cluster.lastElementChild).toBe(pill);
    expect(Array.from(cluster.querySelectorAll('button')).map((b) => b.dataset.testid)).toEqual([
      'global-bar-account-trigger',
      'global-bar-working-trigger',
      'global-bar-tav-trigger',
      'global-bar-account-pill',
    ]);
    // View navigation and the Account icon live on the nav rail now.
    expect(container.querySelector('[data-testid="global-bar-account-nav"]')).toBeNull();
    expect(container.querySelector('[data-testid="global-bar-nav-scanner"]')).toBeNull();
    expect(container.querySelector('[data-testid="global-bar-nav-trader"]')).toBeNull();
    const kids = Array.from(right.children);
    expect(kids.indexOf(wrap)).toBeLessThan(kids.indexOf(lock));
    // The two chips this pill replaces are gone.
    expect(container.querySelector('[data-testid="global-bar-account-type"]')).toBeNull();
    expect(container.querySelector('[data-testid="global-bar-account-id"]')).toBeNull();
  });

  it('omits the class word when account_class is not stamped, keeping the raw AccountType in the tooltip', () => {
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
    const pill = container.querySelector('[data-testid="global-bar-account-pill"]') as HTMLElement;
    expect(pill).toBeTruthy();
    expect(pill.textContent).toContain('Individual (U1234567)');
    expect(pill.textContent).not.toMatch(/Cash|Margin/);
    expect(pill.title).toContain('IBKR AccountType: INDIVIDUAL');
    expect(pill.title).toContain('IBKR TradingType-S: STKNOPT');
    expect(pill.title).toContain('login username is never exposed');
    expect(pill.title).not.toMatch(/\bMargin\b/);
  });

  it('lists the managed accounts under the pill with the active one marked', () => {
    status.current = baseStatus({ account_ids: ['U1234567', 'U7654321'] });
    renderBar();
    const pill = container.querySelector('[data-testid="global-bar-account-pill"]') as HTMLButtonElement;
    expect(pill.title).toContain('Other managed accounts on this login: U7654321');
    act(() => {
      pill.click();
    });
    const items = Array.from(
      container.querySelectorAll('[data-testid="global-bar-account-pill-item"]'),
    );
    expect(items.map((el) => el.getAttribute('data-account-id'))).toEqual(['U1234567', 'U7654321']);
    expect(items[0].getAttribute('aria-current')).toBe('true');
    expect(items[1].getAttribute('aria-current')).toBeNull();
  });

  it('hides the account pill while disconnected -- an old id would be a lie', () => {
    workspace = baseWorkspace({ ibkrConnected: false, ibkrMode: 'disconnected' });
    status.current = baseStatus({ connected: false, mode: 'disconnected' });
    account = baseAccount({ summary: null, orders: [] });
    renderBar();
    expect(container.querySelector('[data-testid="global-bar-account-pill"]')).toBeNull();
  });

  it('shows NOVA-PAPER figures on Paper even though the live Gateway has an IBKR summary too (ADR 020)', () => {
    workspace = baseWorkspace({ ibkrMode: 'paper', ibkrGatewayMode: 'live', ibkrAccountKind: 'live' });
    status.current = baseStatus({
      mode: 'paper',
      venue: 'paper',
      account_id: 'NOVA-PAPER',
      account_ids: ['NOVA-PAPER'],
    });
    practice.current = { data: PAPER_ACCOUNT, error: null };
    renderBar();
    const cluster = container.querySelector('[data-testid="global-bar-cluster"]') as HTMLElement;
    expect(cluster).toBeTruthy();
    expect(cluster.textContent).toContain('+$250.25');
    expect(cluster.textContent).toContain('$101,200.25');
    expect(cluster.textContent).not.toContain('$3,559.55');
    const pill = cluster.querySelector('[data-testid="global-bar-account-pill"]') as HTMLElement;
    expect(pill.textContent).toContain('Nova Paper Margin (NOVA-PAPER)');
    expect(pill.getAttribute('data-kind')).toBe('practice');
    expect(pill.title).toMatch(/fake money/i);
    act(() => {
      (cluster.querySelector('[data-testid="global-bar-tav-trigger"]') as HTMLButtonElement).click();
    });
    expect(
      container.querySelector('[data-testid="global-bar-card-starting-cash"]')?.textContent,
    ).toContain('$100,000.00');
    expect(container.querySelector('[data-testid="global-bar-card-excess"]')).toBeNull();
    act(() => {
      (cluster.querySelector('[data-testid="global-bar-account-trigger"]') as HTMLButtonElement).click();
    });
    expect(container.querySelector('[data-testid="global-bar-card-fees"]')?.textContent).toContain('$3.50');
    // No second row: the practice strip is gone.
    expect(container.querySelector('[data-testid="practice-strip"]')).toBeNull();
  });

  it('shows the NOVA-SIM pill and the replay row on Sim', () => {
    workspace = baseWorkspace({ ibkrMode: 'sim' });
    status.current = baseStatus({ mode: 'sim', venue: 'sim', account_id: 'NOVA-SIM', account_ids: ['NOVA-SIM'] });
    practice.current = {
      data: { ...PAPER_ACCOUNT, venue: 'sim', account_id: 'NOVA-SIM', replay_key: 'capture:AAPL:2026-09-19' },
      error: null,
    };
    renderBar();
    const pill = container.querySelector('[data-testid="global-bar-account-pill"]') as HTMLElement;
    expect(pill.textContent).toContain('Nova Sim Margin (NOVA-SIM)');
    act(() => {
      (container.querySelector('[data-testid="global-bar-tav-trigger"]') as HTMLButtonElement).click();
    });
    expect(container.querySelector('[data-testid="global-bar-card-replay"]')?.textContent).toContain(
      'capture:AAPL:2026-09-19',
    );
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
    const kill = center.querySelector(
      '[data-testid="global-bar-emergency-kill"]',
    ) as HTMLButtonElement;
    expect(kill).toBeTruthy();
    // KILL leads the center column; the status cluster follows it.
    const kids = Array.from(center.children);
    const status = center.querySelector('[data-testid="global-bar-status"]') as HTMLElement;
    expect(kids.indexOf(kill)).toBe(0);
    expect(kids.indexOf(status)).toBe(1);
    // Symbol tabs moved out of the center column to their own row under Bot Autonomy.
    expect(center.querySelector('[data-testid="global-bar-trader-slot"]')).toBeNull();
  });

  it('puts the Trader tab row under Bot Autonomy, outside the primary row', () => {
    workspace = baseWorkspace({
      traderTabs: ['AAPL'],
      activeTraderSymbol: 'AAPL',
      traderViewActive: true,
    });
    act(() => {
      root.render(<GlobalAppBar scanner={scannerProps} />);
    });
    const header = container.querySelector('[data-testid="global-app-bar"]') as HTMLElement;
    const primary = container.querySelector('[data-testid="global-bar-primary"]') as HTMLElement;
    const botRow = container.querySelector('[data-testid="global-bar-bot"]') as HTMLElement;
    const slot = container.querySelector('[data-testid="global-bar-trader-slot"]') as HTMLElement;
    expect(slot).toBeTruthy();
    expect(primary.contains(slot)).toBe(false);
    const kids = Array.from(header.children);
    expect(kids.indexOf(slot)).toBe(kids.indexOf(botRow) + 1);
  });
});
