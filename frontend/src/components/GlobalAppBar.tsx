/**
 * Webull-style single-row chrome shared by Scanner and Trader View.
 * Mounted once in AppShell so every live page inherits it automatically.
 */
import { useEffect, useId, useRef, useState } from 'react';
import {
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
  GLOBAL_BAR_WORKING_LABEL,
  GLOBAL_BAR_WORKING_MENU_TITLE,
} from '../constants';
import { useClosedOrders } from '../closed_orders/useClosedOrders';
import { useIbkrAccountContext } from '../ibkr/IbkrAccountContext';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { formatMoney } from '../utils/formatMoney';
import { GlobalAccountCard } from './GlobalAccountCard';
import { GlobalWorkingMenu } from './GlobalWorkingMenu';
import { dayPnlFromSummary, formatSignedMoney, pnlToneClass } from './globalBarMoney';
import { NovaLogo } from './NovaLogo';

type OpenMenu = 'account' | 'working' | null;

export function GlobalAppBar() {
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
  const [openMenu, setOpenMenu] = useState<OpenMenu>(null);
  const clusterRef = useRef<HTMLDivElement>(null);
  const accountCardId = useId();
  const workingMenuId = useId();

  const traderActive = traderTabs.length > 0;
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

      <div className="global-app-bar__spacer" aria-hidden />

      <div className="global-app-bar__right">
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
      </div>
    </header>
  );
}
