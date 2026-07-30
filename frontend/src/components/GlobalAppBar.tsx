/**
 * Webull-style single-row chrome shared by Scanner and Trader View.
 * Mounted once in AppShell so every live page inherits it automatically.
 */
import { useEffect, useId, useRef, useState } from 'react';
import {
  GLOBAL_BAR_ACCOUNT_LABEL,
  GLOBAL_BAR_ACCOUNT_TITLE,
  GLOBAL_BAR_BRAND,
  GLOBAL_BAR_MODE_DISCONNECTED,
  GLOBAL_BAR_MODE_LIVE,
  GLOBAL_BAR_MODE_PAPER,
  GLOBAL_BAR_NAV_SCANNER,
  GLOBAL_BAR_NAV_SCANNER_TITLE,
  GLOBAL_BAR_NAV_TRADER,
  GLOBAL_BAR_NAV_TRADER_DISABLED_TITLE,
  GLOBAL_BAR_NAV_TRADER_TITLE,
  GLOBAL_BAR_SETTINGS_LABEL,
  GLOBAL_BAR_SETTINGS_TITLE,
} from '../constants';
import { useClosedOrders } from '../closed_orders/useClosedOrders';
import { useIbkrAccountContext } from '../ibkr/IbkrAccountContext';
import { useSettingsOptional } from '../settings/SettingsContext';
import { useModuleVisibility } from '../workspace/useModuleVisibility';
import { useWorkspace } from '../workspace/WorkspaceContext';
import {
  getAccountNavActive,
  subscribeAccountNavActive,
} from './accountNavActive';
import { GlobalBarAccountCluster } from './GlobalBarAccountCluster';
import { resolveAccountChromeState } from './globalBarAccountChrome';
import { NovaLogo } from './NovaLogo';
import { HeaderConnectionStatus } from './HeaderConnectionStatus';
import { SymbolSearchBox } from './SymbolSearchBox';
import { ThemeToggle } from './ThemeToggle';
import { requestOpenTradingTab } from './openTradingTabNav';
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
    openStockView,
    closeTraderView,
    ibkrConnected,
    ibkrMode,
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

  const traderActive = traderTabs.length > 0;
  const settingsOpen = settingsApi?.settings.showSettings ?? false;
  const showAccountNav = visibility.trading !== false;

  useEffect(() => subscribeAccountNavActive(setAccountNavActive), []);
  const canOpenTrader = traderActive || Boolean(selectedSymbol?.trim());
  const accountChrome = resolveAccountChromeState({
    ibkrConnected: Boolean(ibkrConnected),
    summaryConnected: summary?.connected,
    loading: accountLoading,
    error: accountError,
  });
  const workingCount = orders.length;
  const modeLabel =
    ibkrMode === 'paper'
      ? GLOBAL_BAR_MODE_PAPER
      : ibkrMode === 'live'
        ? GLOBAL_BAR_MODE_LIVE
        : GLOBAL_BAR_MODE_DISCONNECTED;

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
              if (traderActive) closeTraderView();
            }}
          >
            {GLOBAL_BAR_NAV_SCANNER}
          </button>
          <button
            type="button"
            className={`global-app-bar__nav-btn${traderActive ? ' is-active' : ''}`}
            aria-pressed={traderActive}
            disabled={!canOpenTrader}
            title={
              canOpenTrader
                ? GLOBAL_BAR_NAV_TRADER_TITLE
                : GLOBAL_BAR_NAV_TRADER_DISABLED_TITLE
            }
            data-testid="global-bar-nav-trader"
            onClick={() => {
              if (traderActive) return;
              const sym = selectedSymbol?.trim().toUpperCase();
              if (sym) openStockView(sym);
            }}
          >
            {GLOBAL_BAR_NAV_TRADER}
          </button>
        </nav>
      </div>

      {scanner && (
        <div className="global-app-bar__scanner" data-testid="global-bar-scanner">
          <span className={`mode-badge mode-${scanner.mode}`}>
            {scanner.sampleDataActive ? 'Sample data' : SCANNER_MODE_LABELS[scanner.mode]}
          </span>
          <HeaderConnectionStatus
            health={scanner.health}
            discoveryProvider={scanner.discoveryProvider}
            ibkrConnected={scanner.ibkrConnected}
            ibkrMode={scanner.ibkrMode}
            ibkrGatewayMode={scanner.ibkrGatewayMode}
            activeFeed={scanner.activeFeed}
            feedFellBack={scanner.feedFellBack}
            secondsAgo={scanner.secondsAgo}
            pricesStale={scanner.pricesStale}
            historyDate={scanner.historyDate}
            compact
            showScannerSource={scanner.showScannerSource ?? true}
            onBackendStarted={scanner.onBackendStarted}
          />
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
      )}

      <div className="global-app-bar__spacer" aria-hidden />

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
            closeTraderView={closeTraderView}
            refresh={refresh}
          />
        </div>

        <span
          className={`global-app-bar__mode global-app-bar__mode--${ibkrMode === 'live' ? 'live' : ibkrMode === 'paper' ? 'paper' : 'off'}`}
          data-testid="global-bar-mode"
          title={modeLabel}
        >
          <span
            className={`global-app-bar__dot${ibkrConnected ? ' is-on' : ''}`}
            aria-hidden
          />
          {modeLabel}
        </span>

        {showAccountNav && (
          <button
            type="button"
            className={`global-app-bar__account-nav${accountNavActive ? ' is-active' : ''}`}
            title={GLOBAL_BAR_ACCOUNT_TITLE}
            aria-pressed={accountNavActive}
            data-testid="global-bar-account-nav"
            onClick={() => {
              requestOpenTradingTab();
              if (traderActive) closeTraderView();
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
    </header>
  );
}
