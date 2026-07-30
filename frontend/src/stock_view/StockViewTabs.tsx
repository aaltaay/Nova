/**
 * Trader View container — tab strip + one StockViewPage per tab.
 * Inactive panes stay mounted (display:none) so L1/L2/tape stay hot.
 */
import { useEffect } from 'react';
import { StockViewPage } from '../pages/StockViewPage';
import {
  leaveStockViewUrl,
  parseStockViewSymbol,
  replaceStockViewUrl,
} from '../utils/stockViewNav';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { StockViewTabStrip } from './StockViewTabStrip';
import { TRADER_DRAFT_SYMBOL } from './traderTabsState';
import './stockViewTabs.css';

interface Props {
  detached: boolean;
}

export function StockViewTabs({ detached }: Props) {
  const {
    traderTabs,
    activeTraderSymbol,
    traderBlockNotice,
    dismissTraderBlockNotice,
    activateTraderTab,
    closeTraderTab,
    renameTraderTab,
    addTraderDraftTab,
    closeTraderView,
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
      closeTraderView();
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

  return (
    <div className="sv-tabs-root" data-testid="sv-tabs-root">
      {traderBlockNotice && (
        <div className="sv-tab-banner" role="status" data-testid="sv-tab-block-banner">
          <span>{traderBlockNotice}</span>
          <button type="button" className="sv-tab-banner__dismiss" onClick={dismissTraderBlockNotice}>
            Dismiss
          </button>
        </div>
      )}
      <StockViewTabStrip
        tabs={traderTabs}
        active={activeTraderSymbol}
        onActivate={onActivate}
        onClose={sym => {
          closeTraderTab(sym);
          if (traderTabs.length <= 1) onBack();
        }}
        onRename={onRename}
        onAddDraft={addTraderDraftTab}
      />
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
                chartActive={show}
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
