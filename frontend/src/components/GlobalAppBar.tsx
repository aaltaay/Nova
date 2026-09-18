/**
 * Webull-style chrome shared by Scanner and Trader View (parent + pop-out).
 * Mounted once in AppShell so every live page inherits it automatically.
 *
 * Primary row = brand, Scanner/Trader, center context, status, theme,
 * account cluster, lock, Cash/Margin, Account, Settings.
 * Bot row = BotArmControls + BotSymbolMenuHost (issue #230).
 * Narrow widths hide low-value chips on the primary row
 * (global-app-bar-responsive.css); the bot row wraps/scrolls on its own.
 */
import { useEffect, useId, useRef, useState } from 'react';
import {
  GLOBAL_BAR_ACCOUNT_LABEL,
  GLOBAL_BAR_ACCOUNT_TITLE,
  GLOBAL_BAR_BRAND,
  GLOBAL_BAR_NAV_SCANNER,
  GLOBAL_BAR_NAV_SCANNER_TITLE,
  TRADER_DEFAULT_SYMBOL,
  GLOBAL_BAR_SETTINGS_LABEL,
  GLOBAL_BAR_SETTINGS_TITLE,
} from '../constants';
import { useClosedOrders } from '../closed_orders/useClosedOrders';
import { FundAccountButton } from '../ibkr/FundAccountButton';
import { useIbkrAccountContext } from '../ibkr/IbkrAccountContext';
import { IbkrAccountTypeChip } from '../ibkr/IbkrAccountTypeChip';
import { TradingSessionLockButton } from '../ibkr/TradingSessionLockButton';
import { useSettingsOptional } from '../settings/SettingsContext';
import { useModuleVisibility } from '../workspace/useModuleVisibility';
import { parseStockViewSymbol } from '../utils/stockViewNav';
import { useWorkspace } from '../workspace/WorkspaceContext';
import {
  getAccountNavActive,
  subscribeAccountNavActive,
} from './accountNavActive';
import { GlobalBarAccountCluster } from './GlobalBarAccountCluster';
import { resolveAccountChromeState } from './globalBarAccountChrome';
import { NovaLogo } from './NovaLogo';
import { GatewayModeCapsule } from '../ibkr/GatewayModeCapsule';
import { setGlobalBarTraderSlot } from './globalBarSlots';
import { HeaderConnectionStatus } from './HeaderConnectionStatus';
import { SymbolSearchBox } from './SymbolSearchBox';
import { GlobalBarBotRow } from '../bot/GlobalBarBotRow';
import { ThemeToggle } from './ThemeToggle';
import { requestOpenTradingTab } from './openTradingTabNav';
import { TraderNavButton } from './TraderNavButton';
import { useScannerBarProps } from './scannerBarStore';
import {
  fmtHistoryDateShort,
  SCANNER_MODE_LABELS,
  type GlobalAppBarScanner,
} from './globalAppBarScanner';

export type { GlobalAppBarScanner };

type OpenMenu = 'account' | 'working' | null;

export function GlobalAppBar({ scanner: scannerProp }: { scanner?: GlobalAppBarScanner }) {
  const liveScanner = useScannerBarProps();
  const scanner = scannerProp ?? liveScanner ?? undefined;
  const {
    selectedSymbol,
    traderTabs,
    traderViewActive,
    openStockView,
    closeTraderView,
    showScannerView,
    ibkrConnected,
    ibkrMode,
    ibkrGatewayMode,
    ibkrAccountKind,
    ibkrIntentionalMode,
    ibkrDisconnectHint,
  } = useWorkspace();
  const { summary, orders, refresh, loading: accountLoading, error: accountError } =
    useIbkrAccountContext();
  const { orders: closedOrders } = useClosedOrders(ibkrConnected);
  const settingsApi = useSettingsOptional();
  const { visibility } = useModuleVisibility();
  const [openMenu, setOpenMenu] = useState<OpenMenu>(null);
  const [accountNavActive, setAccountNavActive] = useState(getAccountNavActive);
  const clusterRef = useRef<HTMLDivElement>(null);
  const accountCardId = useId();
  const workingMenuId = useId();

  const traderActive = traderViewActive;
  const detachedTrader = traderTabs.length > 0 && parseStockViewSymbol() != null;
  const leaveTraderToScanner = () => {
    if (!traderViewActive) return;
    if (detachedTrader) closeTraderView();
    else showScannerView();
  };
  const settingsOpen = settingsApi?.settings.showSettings ?? false;
  const showAccountNav = visibility.trading !== false;

  useEffect(() => subscribeAccountNavActive(setAccountNavActive), []);
  const traderSymbol = (selectedSymbol?.trim() || TRADER_DEFAULT_SYMBOL).toUpperCase();
  const accountChrome = resolveAccountChromeState({
    ibkrConnected: Boolean(ibkrConnected),
    summaryConnected: summary?.connected,
    loading: accountLoading,
    error: accountError,
  });
  const workingCount = orders.length;

  useEffect(() => {
    if (!openMenu) return;
    const onDoc = (e: MouseEvent) => {
      if (!clusterRef.current?.contains(e.target as Node)) setOpenMenu(null);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpenMenu(null);
    };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [openMenu]);

  return (
    <header className="global-app-bar" data-testid="global-app-bar">
      <div className="global-app-bar__primary" data-testid="global-bar-primary">
      <div className="global-app-bar__left">
        <div className="global-app-bar__brand" aria-label={GLOBAL_BAR_BRAND}>
          <NovaLogo />
          <span className="global-app-bar__wordmark">{GLOBAL_BAR_BRAND}</span>
        </div>
        <nav className="global-app-bar__nav" aria-label="Primary views">
          <button
            type="button"
            className={`global-app-bar__nav-btn${!traderActive ? ' is-active' : ''}`}
            aria-pressed={!traderActive}
            title={GLOBAL_BAR_NAV_SCANNER_TITLE}
            data-testid="global-bar-nav-scanner"
            onClick={() => {
              leaveTraderToScanner();
            }}
          >
            {GLOBAL_BAR_NAV_SCANNER}
          </button>
          <TraderNavButton
            traderActive={traderActive}
            traderSymbol={traderSymbol}
            onOpen={openStockView}
          />
        </nav>
      </div>

      <div className="global-app-bar__center" data-testid="global-bar-center">
        {traderActive ? (
          <div
            ref={setGlobalBarTraderSlot}
            className="global-app-bar__context global-app-bar__trader-slot"
            data-testid="global-bar-trader-slot"
          />
        ) : (
          scanner && (
            <div
              className="global-app-bar__context global-app-bar__scanner"
              data-testid="global-bar-scanner"
            >
              {scanner.onSampleDataToggle && (
                <label
                  className={`sample-data-switch${scanner.sampleDataActive ? ' sample-data-switch--on' : ''}`}
                  title="Open isolated sample fixtures — never mixed with live market data"
                  data-testid="sample-data-switch"
                >
                  <input
                    type="checkbox"
                    checked={scanner.sampleDataActive}
                    onChange={(e) => scanner.onSampleDataToggle?.(e.target.checked)}
                  />
                  <span>Sample</span>
                </label>
              )}
              <select
                className={`history-select${scanner.historyDate ? ' history-select--active' : ''}`}
                value={scanner.historyDate ?? ''}
                onChange={scanner.onHistoryChange}
                title="Browse historical snapshots"
                disabled={scanner.sampleDataActive}
              >
                <option value="">{scanner.sampleDataActive ? 'Sample (fixtures)' : 'Today (Live)'}</option>
                {!scanner.sampleDataActive &&
                  scanner.historyDates.map((d) => (
                    <option key={d} value={d}>
                      {fmtHistoryDateShort(d)}
                    </option>
                  ))}
              </select>
              <SymbolSearchBox onLookup={scanner.onLookup} />
            </div>
          )
        )}
        {scanner && (
          <div className="global-app-bar__status" data-testid="global-bar-status">
            <span className={`mode-badge mode-${scanner.mode}`}>
              {scanner.sampleDataActive ? 'Sample data' : SCANNER_MODE_LABELS[scanner.mode]}
            </span>
            <HeaderConnectionStatus
              health={scanner.health}
              discoveryProvider={scanner.discoveryProvider}
              ibkrConnected={scanner.ibkrConnected}
              ibkrMode={scanner.ibkrMode}
              ibkrGatewayMode={scanner.ibkrGatewayMode}
              ibkrAccountKind={ibkrAccountKind}
              ibkrIntentionalMode={ibkrIntentionalMode}
              activeFeed={scanner.activeFeed}
              feedFellBack={scanner.feedFellBack}
              secondsAgo={scanner.secondsAgo}
              lastPriceTs={scanner.lastPriceTs}
              pricesStale={scanner.pricesStale}
              honestyText={scanner.honestyText}
              historyDate={scanner.historyDate}
              compact
              showScannerSource={scanner.showScannerSource ?? true}
              onBackendStarted={scanner.onBackendStarted}
            />
          </div>
        )}
      </div>

      <div className="global-app-bar__right">
        <ThemeToggle />
        <div
          className="global-app-bar__account"
          ref={clusterRef}
          data-testid="global-bar-account"
        >
          <GlobalBarAccountCluster
            accountChrome={accountChrome}
            accountError={accountError}
            summary={summary}
            orders={orders}
            workingCount={workingCount}
            openMenu={openMenu}
            setOpenMenu={setOpenMenu}
            accountCardId={accountCardId}
            workingMenuId={workingMenuId}
            closedOrders={closedOrders}
            traderActive={traderActive}
            closeTraderView={leaveTraderToScanner}
            refresh={refresh}
          />
        </div>

        {!scanner && (
          <GatewayModeCapsule
            mode={ibkrMode}
            gatewayMode={ibkrGatewayMode ?? undefined}
            accountKind={ibkrAccountKind}
            intentionalMode={ibkrIntentionalMode}
            disconnectHint={ibkrDisconnectHint}
            testId="header-gateway-mode-capsule"
          />
        )}

        <TradingSessionLockButton />
        <IbkrAccountTypeChip
          ibkrConnected={Boolean(ibkrConnected)}
          summary={summary}
        />
        <FundAccountButton />

        {showAccountNav && (
          <button
            type="button"
            className={`global-app-bar__account-nav${accountNavActive ? ' is-active' : ''}`}
            title={GLOBAL_BAR_ACCOUNT_TITLE}
            aria-pressed={accountNavActive}
            data-testid="global-bar-account-nav"
            onClick={() => {
              requestOpenTradingTab();
              leaveTraderToScanner();
            }}
          >
            {GLOBAL_BAR_ACCOUNT_LABEL}
          </button>
        )}

        {settingsApi && (
          <button
            type="button"
            className={`global-app-bar__settings${settingsOpen ? ' is-active' : ''}`}
            title={GLOBAL_BAR_SETTINGS_TITLE}
            aria-pressed={settingsOpen}
            data-testid="global-bar-settings"
            onClick={() => settingsApi.toggleSettings()}
          >
            {GLOBAL_BAR_SETTINGS_LABEL}
          </button>
        )}
      </div>
      </div>
      <GlobalBarBotRow />
    </header>
  );
}
