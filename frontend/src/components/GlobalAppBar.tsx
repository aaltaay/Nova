/**
 * Webull-style single-row chrome shared by Scanner and Trader View.
 * Mounted once in AppShell so every live page inherits it automatically.
 */
import { useEffect, useId, useRef, useState } from 'react';
import {
  GLOBAL_BAR_ACCOUNT_LABEL,
  GLOBAL_BAR_ACCOUNT_TITLE,
  GLOBAL_BAR_BP_LABEL,
  GLOBAL_BAR_BRAND,
  GLOBAL_BAR_DAY_PNL_LABEL,
  GLOBAL_BAR_MODE_DISCONNECTED,
  GLOBAL_BAR_MODE_LIVE,
  GLOBAL_BAR_MODE_PAPER,
  GLOBAL_BAR_NAV_SCANNER,
  GLOBAL_BAR_NAV_SCANNER_TITLE,
  GLOBAL_BAR_NAV_TRADER,
  GLOBAL_BAR_NAV_TRADER_DISABLED_TITLE,
  GLOBAL_BAR_NAV_TRADER_TITLE,
  GLOBAL_BAR_NET_LIQ_LABEL,
  GLOBAL_BAR_OFFLINE_CHIP,
  GLOBAL_BAR_OFFLINE_PLACEHOLDER,
  GLOBAL_BAR_SETTINGS_LABEL,
  GLOBAL_BAR_SETTINGS_TITLE,
  GLOBAL_BAR_WORKING_LABEL,
  GLOBAL_BAR_WORKING_MENU_TITLE,
} from '../constants';
import { useClosedOrders } from '../closed_orders/useClosedOrders';
import { useIbkrAccountContext } from '../ibkr/IbkrAccountContext';
import { useSettingsOptional } from '../settings/SettingsContext';
import { useModuleVisibility } from '../workspace/useModuleVisibility';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { formatMoney } from '../utils/formatMoney';
import {
  getAccountNavActive,
  subscribeAccountNavActive,
} from './accountNavActive';
import { GlobalAccountCard } from './GlobalAccountCard';
import { GlobalWorkingMenu } from './GlobalWorkingMenu';
import { dayPnlFromSummary, formatSignedMoney, pnlToneClass } from './globalBarMoney';
import { NovaLogo } from './NovaLogo';
import { HeaderConnectionStatus } from './HeaderConnectionStatus';
import { SymbolSearchBox } from './SymbolSearchBox';
import { ThemeToggle } from './ThemeToggle';
import { requestOpenTradingTab } from './openTradingTabNav';
import { useScannerBarProps } from './scannerBarBridge';

type OpenMenu = 'account' | 'working' | null;

/** Scanner-only status block (market mode, chips, history, lookup) merged into this bar. */
import type { HealthStatus } from '../types/health';
import type { IbkrMode } from '../ibkr/types';

export type GlobalAppBarScanner = {
  mode: 'premarket' | 'market' | 'afterhours' | 'closed' | 'loading';
  health: HealthStatus;
  activeFeed: string;
  feedFellBack: boolean;
  secondsAgo: number | null;
  pricesStale?: boolean;
  ibkrConnected?: boolean;
  ibkrMode?: IbkrMode;
  ibkrGatewayMode?: 'paper' | 'live' | null;
  historyDate: string | null;
  historyDates: string[];
  onHistoryChange: (e: React.ChangeEvent<HTMLSelectElement>) => void;
  onLookup: (symbol: string) => void;
  showScannerSource?: boolean;
  discoveryProvider?: string;
  onBackendStarted?: () => void;
  sampleDataActive?: boolean;
  onSampleDataToggle?: (active: boolean) => void;
};

const SCANNER_MODE_LABELS: Record<GlobalAppBarScanner['mode'], string> = {
  loading: 'Connecting…',
  premarket: 'Pre-Market',
  market: 'Market Hours',
  afterhours: 'After Hours',
  closed: 'Market Closed',
};

function fmtHistoryDateShort(dateStr: string): string {
  const [y, m, d] = dateStr.split('-').map(Number);
  const dt = new Date(y, m - 1, d);
  return dt.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
}

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
  const { summary, orders, refresh } = useIbkrAccountContext();
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
  const live = Boolean(ibkrConnected && summary?.connected);
  const dayPnl = dayPnlFromSummary(summary?.RealizedPnL, summary?.UnrealizedPnL);
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
          {live ? (
            <div className="global-app-bar__cluster" data-testid="global-bar-cluster">
              <button
                type="button"
                className="global-app-bar__metric-btn global-app-bar__metric--day"
                aria-expanded={openMenu === 'account'}
                aria-controls={accountCardId}
                data-testid="global-bar-account-trigger"
                onClick={() =>
                  setOpenMenu(m => (m === 'account' ? null : 'account'))
                }
                onMouseEnter={() => setOpenMenu('account')}
              >
                <label>{GLOBAL_BAR_DAY_PNL_LABEL}</label>
                <span className={pnlToneClass(dayPnl)}>{formatSignedMoney(dayPnl)}</span>
              </button>
              <span className="global-app-bar__sep" aria-hidden />
              <button
                type="button"
                className="global-app-bar__metric-btn global-app-bar__metric--netliq"
                aria-expanded={openMenu === 'account'}
                onClick={() =>
                  setOpenMenu(m => (m === 'account' ? null : 'account'))
                }
                onMouseEnter={() => setOpenMenu('account')}
              >
                <label>{GLOBAL_BAR_NET_LIQ_LABEL}</label>
                <span>{formatMoney(summary?.NetLiquidation)}</span>
              </button>
              <span className="global-app-bar__sep global-app-bar__sep--bp" aria-hidden />
              <button
                type="button"
                className="global-app-bar__metric-btn global-app-bar__metric--bp"
                aria-expanded={openMenu === 'account'}
                onClick={() =>
                  setOpenMenu(m => (m === 'account' ? null : 'account'))
                }
                onMouseEnter={() => setOpenMenu('account')}
              >
                <label>{GLOBAL_BAR_BP_LABEL}</label>
                <span>{formatMoney(summary?.BuyingPower)}</span>
              </button>
              <span className="global-app-bar__sep" aria-hidden />
              <button
                type="button"
                className="global-app-bar__metric-btn global-app-bar__metric--working"
                aria-expanded={openMenu === 'working'}
                aria-controls={workingMenuId}
                aria-label={GLOBAL_BAR_WORKING_MENU_TITLE}
                data-testid="global-bar-working-trigger"
                onClick={() =>
                  setOpenMenu(m => (m === 'working' ? null : 'working'))
                }
                onMouseEnter={() => setOpenMenu('working')}
              >
                <label>{GLOBAL_BAR_WORKING_LABEL}</label>
                <span className="global-app-bar__working-count">{workingCount}</span>
                <span className="global-app-bar__caret" aria-hidden>
                  {openMenu === 'working' ? '▴' : '▾'}
                </span>
              </button>
            </div>
          ) : (
            <div
              className="global-app-bar__cluster global-app-bar__cluster--offline"
              data-testid="global-bar-offline"
            >
              <span className="global-app-bar__offline-chip">{GLOBAL_BAR_OFFLINE_CHIP}</span>
              <span className="global-app-bar__sep" aria-hidden />
              <span className="global-app-bar__metric">
                <label>{GLOBAL_BAR_NET_LIQ_LABEL}</label>
                <span>{GLOBAL_BAR_OFFLINE_PLACEHOLDER}</span>
              </span>
            </div>
          )}
          {openMenu === 'account' && live && (
            <div id={accountCardId}>
              <GlobalAccountCard summary={summary} />
            </div>
          )}
          {openMenu === 'working' && live && (
            <div id={workingMenuId}>
              <GlobalWorkingMenu
                workingOrders={orders}
                closedOrders={closedOrders}
                traderActive={traderActive}
                closeTraderView={closeTraderView}
                onRefresh={refresh}
                onClose={() => setOpenMenu(null)}
              />
            </div>
          )}
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
