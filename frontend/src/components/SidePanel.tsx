/** Scanner side panel — quote, panel chart, fundamentals for selectedSymbol.
 * It folds to a strip on the right edge (like the Trader's Focus list folds
 * left); folded, it streams nothing. */
import { useEffect, useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import {
  QUOTE_PANEL_STALE_LABEL,
  QUOTE_PANEL_TITLE,
  STOCK_VIEW_OPEN_LABEL,
  STOCK_VIEW_OPEN_TITLE,
} from '../constants';
import {
  QUOTE_PANEL_COLLAPSE,
  QUOTE_PANEL_EXPAND,
  QUOTE_PANEL_LOOKUP_ARIA,
  QUOTE_PANEL_LOOKUP_LABEL,
  QUOTE_PANEL_LOOKUP_PLACEHOLDER,
} from '../constantGroups/scanner_board';
import { useTickerStream } from '../hooks/useTickerStream';
import type { WatchlistEntry } from '../strategy/types';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { TickerDetailContent } from './TickerDetailContent';
import './sidePanelCollapse.css';

interface Props {
  /** Live watchlist ranks from App's useWatchlist poll — used for the side-panel strip. */
  watchlistEntries?: WatchlistEntry[];
  /** User-resized width from the drag splitter (ignored when stacked on narrow viewports). */
  widthPx?: number;
  /** Folded to the right-edge strip (useQuotePanelCollapsed). */
  collapsed?: boolean;
  /** Fold / unfold; omitted, the panel has no collapse control. */
  onToggleCollapsed?: () => void;
}

export function SidePanel({
  watchlistEntries = [],
  widthPx,
  collapsed = false,
  onToggleCollapsed,
}: Props) {
  const {
    selectedSymbol,
    setSelectedSymbol,
    openStockView,
  } = useWorkspace();
  const [input, setInput] = useState(selectedSymbol ?? '');
  // Folded, the panel shows no quote, so it holds no stream (and no IBKR line) for one.
  const { detail, loading, refreshing, fetchFailed, stale, disconnectedSince } =
    useTickerStream(collapsed ? null : selectedSymbol);

  const watchlistIndex = useMemo(
    () => (selectedSymbol ? watchlistEntries.findIndex(e => e.symbol === selectedSymbol) : -1),
    [selectedSymbol, watchlistEntries],
  );
  const watchlistEntry = watchlistIndex >= 0 ? watchlistEntries[watchlistIndex] : null;

  // One render happens after selecting a symbol before the WS effect runs; without this,
  // loading/refreshing are still false and detail is null → a false "No data" flash.
  const awaitingPreEffectFrame =
    !!selectedSymbol && detail == null && !loading && !refreshing && !fetchFailed;
  const showFullSpinner = loading || awaitingPreEffectFrame;

  useEffect(() => {
    setInput(selectedSymbol ?? '');
  }, [selectedSymbol]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const sym = input.trim().toUpperCase();
    setSelectedSymbol(sym || null);
  }

  if (collapsed) {
    return (
      <aside className="side-panel side-panel--collapsed" data-testid="quote-panel" data-collapsed="1" aria-label={QUOTE_PANEL_TITLE}>
        <button type="button" className="side-panel__expand" aria-label={QUOTE_PANEL_EXPAND} title={QUOTE_PANEL_EXPAND}
          data-testid="quote-panel-expand" onClick={onToggleCollapsed}>
          <ChevronLeft size={14} aria-hidden="true" />
          <span className="side-panel__vertical">{QUOTE_PANEL_TITLE}{selectedSymbol ? ` · ${selectedSymbol}` : ''}</span>
        </button>
      </aside>
    );
  }

  return (
    <aside
      className="side-panel"
      data-testid="quote-panel"
      data-collapsed="0"
      style={widthPx != null ? { width: widthPx, maxWidth: 'none' } : undefined}
    >
      <div className="side-panel-search">
        <form className="side-search-form" onSubmit={handleSubmit}>
          <input
            className="side-search-input"
            type="text"
            value={input}
            onChange={e => setInput(e.target.value.toUpperCase())}
            placeholder={QUOTE_PANEL_LOOKUP_PLACEHOLDER}
            autoComplete="off"
            spellCheck={false}
            aria-label={QUOTE_PANEL_LOOKUP_ARIA}
          />
          <button type="submit" className="side-search-btn">{QUOTE_PANEL_LOOKUP_LABEL}</button>
        </form>
        {selectedSymbol && (
          <button
            type="button"
            className="side-open-trading-btn"
            onClick={() => openStockView(selectedSymbol)}
            title={STOCK_VIEW_OPEN_TITLE}
          >
            {STOCK_VIEW_OPEN_LABEL}
          </button>
        )}
        {onToggleCollapsed && (
          <button type="button" className="side-panel__collapse" aria-label={QUOTE_PANEL_COLLAPSE} title={QUOTE_PANEL_COLLAPSE}
            data-testid="quote-panel-collapse" onClick={onToggleCollapsed}>
            <ChevronRight size={14} aria-hidden="true" />
          </button>
        )}
      </div>
      <div className="side-panel-body">
        <div className="quote-panel-title" title="Scanner sidebar quote — same data as Trader">
          {QUOTE_PANEL_TITLE}
        </div>
        {showFullSpinner && (
          <div className="detail-loading">
            <div className="detail-loading-spinner" />
            <span>Loading…</span>
          </div>
        )}
        {!showFullSpinner && selectedSymbol && refreshing && detail?.symbol === selectedSymbol && (
          <div className="detail-refreshing-bar">
            <div className="detail-loading-spinner detail-loading-spinner--small" />
            <span>Updating {selectedSymbol}…</span>
          </div>
        )}
        {!showFullSpinner && selectedSymbol && stale && detail?.symbol === selectedSymbol && (
          <div
            className="detail-stale-bar"
            role="status"
            data-testid="quote-stale-badge"
            title={QUOTE_PANEL_STALE_LABEL}
          >
            {QUOTE_PANEL_STALE_LABEL}
            {disconnectedSince != null
              ? ` · last live ${new Date(disconnectedSince).toLocaleTimeString()}`
              : ''}
          </div>
        )}
        {!showFullSpinner && selectedSymbol && detail?.symbol === selectedSymbol && (
          <div className="detail-body">
            <TickerDetailContent
              detail={detail}
              selectedSymbol={selectedSymbol}
              showChart
              layout="columns"
              layoutSlot="side_panel"
              watchlistEntry={watchlistEntry}
              watchlistRank={watchlistIndex >= 0 ? watchlistIndex + 1 : null}
            />
          </div>
        )}
        {!showFullSpinner && fetchFailed && !(detail?.symbol === selectedSymbol) && selectedSymbol && (
          <div className="detail-empty">No data found for {selectedSymbol}.</div>
        )}
        {!showFullSpinner && !selectedSymbol && (
          <div className="detail-empty">Enter a ticker symbol above to look up a stock quote.</div>
        )}
      </div>
    </aside>
  );
}
