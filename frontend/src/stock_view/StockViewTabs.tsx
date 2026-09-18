/**
 * Trader View container — tab strip + one StockViewPage per tab.
 * Inactive live panes stay mounted (hidden) so L1/L2/tape sockets stay
 * subscribed. Tape/depth/chart UI apply pauses until the tab is shown again.
 * The tab strip portals into GlobalAppBar's middle column when that slot is
 * mounted (one header row), else renders inline above the panes.
 */
import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { useGlobalBarTraderSlot } from '../components/globalBarSlots';
import { StockViewPage } from '../pages/StockViewPage';
import {
  leaveStockViewUrl,
  parseStockViewSymbol,
  replaceStockViewUrl,
} from '../utils/stockViewNav';
import { useWorkspace } from '../workspace/WorkspaceContext';
import {
  allowTraderTabDrop,
  canExtractFromDesk,
  isForeignTabDrag,
  takeForeignTraderTabDrop,
} from '../workspace/traderDesk';
import { StockViewTabStrip } from './StockViewTabStrip';
import { TRADER_DRAFT_SYMBOL } from './traderTabsState';
import './stockViewTabs.css';

interface Props {
  detached: boolean;
}

export function StockViewTabs({ detached }: Props) {
  const {
    traderTabs,
    traderLiveTabs,
    activeTraderSymbol,
    traderBlockNotice,
    dismissTraderBlockNotice,
    activateTraderTab,
    closeTraderTab,
    renameTraderTab,
    addTraderDraftTab,
    extractTraderTab,
    acceptTraderTabDrop,
    requestDockTraderTab,
    traderWindowId,
    traderDeskRole,
    traderDockOffer,
    publishTraderTabOffer,
    publishTraderTabOfferEnd,
    closeTraderView,
    showScannerView,
    traderViewActive,
    setSelectedSymbol,
  } = useWorkspace();

  useEffect(() => {
    if (!detached) return;
    const active = activeTraderSymbol;
    if (active && active !== TRADER_DRAFT_SYMBOL) {
      replaceStockViewUrl(active);
    }
  }, [detached, activeTraderSymbol]);

  const onBack = () => {
    if (detached) {
      leaveStockViewUrl();
      if (window.opener) window.close();
      else closeTraderView();
    } else {
      showScannerView();
    }
  };

  const onRename = (from: string, to: string) => {
    renameTraderTab(from, to);
    const next = to.trim().toUpperCase();
    if (next) setSelectedSymbol(next);
  };

  const onActivate = (symbol: string) => {
    activateTraderTab(symbol);
    if (symbol && symbol !== TRADER_DRAFT_SYMBOL) {
      setSelectedSymbol(symbol);
    }
  };

  const dropReady = Boolean(
    traderDockOffer && isForeignTabDrag(traderDockOffer.sourceWindowId, traderWindowId),
  );
  const headerSlot = useGlobalBarTraderSlot();

  const tabStrip = (
    <StockViewTabStrip
      tabs={traderTabs}
      live={traderLiveTabs}
      active={activeTraderSymbol}
      windowId={traderWindowId}
      showDock={traderDeskRole === 'float'}
      showExtract={canExtractFromDesk(traderDeskRole)}
      dropReady={dropReady}
      onActivate={onActivate}
      onClose={sym => {
        closeTraderTab(sym);
        if (traderTabs.length <= 1) onBack();
      }}
      onRename={onRename}
      onAddDraft={addTraderDraftTab}
      onExtract={extractTraderTab}
      onDock={requestDockTraderTab}
      onTabDragStart={publishTraderTabOffer}
      onTabDragEnd={publishTraderTabOfferEnd}
      onTabDrop={acceptTraderTabDrop}
    />
  );

  return (
    <div
      className={`sv-tabs-root${dropReady ? ' sv-tabs-root--drop-ready' : ''}`}
      data-testid="sv-tabs-root"
      onDragOver={allowTraderTabDrop}
      onDrop={(e) => {
        const payload = takeForeignTraderTabDrop(e, traderWindowId);
        if (payload) acceptTraderTabDrop(payload);
      }}
    >
      {traderBlockNotice && (
        <div className="sv-tab-banner" role="status" data-testid="sv-tab-block-banner">
          <span>{traderBlockNotice}</span>
          <button type="button" className="sv-tab-banner__dismiss" onClick={dismissTraderBlockNotice}>
            Dismiss
          </button>
        </div>
      )}
      {headerSlot && traderViewActive ? createPortal(tabStrip, headerSlot) : tabStrip}
      <div className="sv-tabs-panes">
        {traderTabs.map(symbol => {
          if (symbol === TRADER_DRAFT_SYMBOL) {
            const show = activeTraderSymbol === TRADER_DRAFT_SYMBOL;
            return (
              <div
                key="__draft__"
                className="sv-tabs-pane sv-tabs-pane--draft"
                hidden={!show}
                aria-hidden={!show}
              >
                <p className="sv-tabs-draft-hint">Type a ticker in the tab above, then press Enter.</p>
              </div>
            );
          }
          const show = symbol === activeTraderSymbol;
          const live = traderLiveTabs.includes(symbol);
          if (!live) {
            return (
              <div
                key={symbol}
                className="sv-tabs-pane sv-tabs-pane--suspended"
                hidden={!show}
                aria-hidden={!show}
                data-testid={`sv-tab-pane-${symbol}`}
                data-suspended="1"
              />
            );
          }
          return (
            <div
              key={symbol}
              className="sv-tabs-pane"
              hidden={!show}
              aria-hidden={!show}
              data-testid={`sv-tab-pane-${symbol}`}
            >
              <StockViewPage
                symbol={symbol}
                detached={detached}
                onBack={onBack}
                onSelectSymbol={next => onRename(symbol, next)}
                chartActive={show && traderViewActive}
              />
            </div>
          );
        })}
      </div>
      {/* Keep parse helper referenced so detached detection stays honest in tests */}
      <span className="sv-tabs-detached-flag" data-detached={detached || parseStockViewSymbol() != null ? '1' : '0'} hidden />
    </div>
  );
}
