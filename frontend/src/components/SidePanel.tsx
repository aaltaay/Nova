/** Scanner side panel — quote, panel chart, fundamentals for selectedSymbol.
 * It folds to a strip on the right edge (like the Trader's Focus list folds
 * left); folded, it streams nothing. */
import { useEffect, useMemo, useState, type ReactNode } from 'react';
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
import { replayPanelDetail, useHistoricalSnapshot, useSimReplayTarget } from '../sim';
import type { WatchlistEntry } from '../strategy/types';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { TickerDetailContent } from './TickerDetailContent';
import './sidePanelCollapse.css';

interface Props {
  /** Live watchlist ranks from App's useWatchlist poll — used for the side-panel strip (never off the Sim live edge). */
  watchlistEntries?: WatchlistEntry[];
  /** User-resized width from the drag splitter (ignored when stacked on narrow viewports). */
  widthPx?: number;
  /** Folded to the right-edge strip (useQuotePanelCollapsed). */
  collapsed?: boolean;
  /** Fold / unfold; omitted, the panel has no collapse control. */
  onToggleCollapsed?: () => void;
  /**
   * The Sim tab notice for the symbol here (the page composes it: shared UI imports
   * no feature internals). `select` loads a symbol in this panel.
   */
  simNotice?: (symbol: string, select: (symbol: string) => void) => ReactNode;
}

export function SidePanel({
  watchlistEntries = [],
  widthPx,
  collapsed = false,
  onToggleCollapsed,
  simNotice,
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

  // A Sim desk off the live edge replays one stock-day: any other symbol here is
  // not the replay, so today's live price must not show over it, and the panel
  // says so with the way to load it -- the Trader tab's own rule and notice. The
  // replay's own symbol shows the replay's quote at the playhead, and the company
  // figures Nova holds only for today are left out, saying so (operator report, 2026-10-12).
  const { sim, clock } = useSimReplayTarget(selectedSymbol ?? '');
  const symbolUpper = (selectedSymbol ?? '').toUpperCase();
  const historical = useHistoricalSnapshot(
    symbolUpper,
    !collapsed && sim && clock?.replay_source === 'historical' && (clock.replay_symbol ?? '').toUpperCase() === symbolUpper,
  );
  const replay = replayPanelDetail(detail, symbolUpper, clock, sim, historical);
  const view = replay.detail;

  // Today's Contenders rank is live: on the Sim venue it holds only at the live edge.
  // Off it the strip asks the backend, which grades the replayed day's own row.
  const liveRanks = !sim || clock?.live_edge === true;
  const watchlistIndex = useMemo(
    () => (selectedSymbol && liveRanks ? watchlistEntries.findIndex(e => e.symbol === selectedSymbol) : -1),
    [selectedSymbol, watchlistEntries, liveRanks],
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
        {selectedSymbol && sim && simNotice?.(selectedSymbol, setSelectedSymbol)}
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
        {!showFullSpinner && selectedSymbol && view && detail?.symbol === selectedSymbol && (
          <div className="detail-body">
            <TickerDetailContent
              detail={view}
              selectedSymbol={selectedSymbol}
              showChart
              layout="columns"
              layoutSlot="side_panel"
              watchlistEntry={watchlistEntry}
              watchlistRank={watchlistIndex >= 0 ? watchlistIndex + 1 : null}
              replayNote={replay.note}
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
