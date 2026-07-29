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
} from '../constants';
import { useIbkrAccountContext } from '../ibkr/IbkrAccountContext';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { formatMoney } from '../utils/formatMoney';
import { GlobalAccountCard } from './GlobalAccountCard';
import { dayPnlFromSummary, formatSignedMoney, pnlToneClass } from './globalBarMoney';
import { NovaLogo } from './NovaLogo';

export function GlobalAppBar() {
  const {
    selectedSymbol,
    traderTabs,
    openStockView,
    closeTraderView,
    ibkrConnected,
    ibkrMode,
  } = useWorkspace();
  const { summary, orders } = useIbkrAccountContext();
  const [cardOpen, setCardOpen] = useState(false);
  const clusterRef = useRef<HTMLDivElement>(null);
  const cardId = useId();

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
    if (!cardOpen) return;
    const onDoc = (e: MouseEvent) => {
      if (!clusterRef.current?.contains(e.target as Node)) setCardOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setCardOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [cardOpen]);

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
            <button
              type="button"
              className="global-app-bar__cluster"
              aria-expanded={cardOpen}
              aria-controls={cardId}
              data-testid="global-bar-cluster"
              onClick={() => setCardOpen(v => !v)}
              onMouseEnter={() => setCardOpen(true)}
            >
              <span className="global-app-bar__metric global-app-bar__metric--day">
                <label>{GLOBAL_BAR_DAY_PNL_LABEL}</label>
                <span className={pnlToneClass(dayPnl)}>{formatSignedMoney(dayPnl)}</span>
              </span>
              <span className="global-app-bar__sep" aria-hidden />
              <span className="global-app-bar__metric global-app-bar__metric--netliq">
                <label>{GLOBAL_BAR_NET_LIQ_LABEL}</label>
                <span>{formatMoney(summary?.NetLiquidation)}</span>
              </span>
              <span className="global-app-bar__sep global-app-bar__sep--bp" aria-hidden />
              <span className="global-app-bar__metric global-app-bar__metric--bp">
                <label>{GLOBAL_BAR_BP_LABEL}</label>
                <span>{formatMoney(summary?.BuyingPower)}</span>
              </span>
              <span className="global-app-bar__sep" aria-hidden />
              <span className="global-app-bar__metric">
                <label>{GLOBAL_BAR_WORKING_LABEL}</label>
                <span className="global-app-bar__working-count">{workingCount}</span>
              </span>
            </button>
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
          {cardOpen && live && (
            <div id={cardId}>
              <GlobalAccountCard summary={summary} workingCount={workingCount} />
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
