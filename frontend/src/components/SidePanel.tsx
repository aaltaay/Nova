/** Scanner side panel — quote, panel chart, fundamentals for selectedSymbol. */
import { useEffect, useMemo, useState } from 'react';
import {
  QUOTE_PANEL_TITLE,
  STOCK_VIEW_OPEN_LABEL,
  STOCK_VIEW_OPEN_TITLE,
} from '../constants';
import { useTickerStream } from '../hooks/useTickerStream';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import type { WatchlistEntry } from '../strategy/types';
import { TickerDetailContent } from './TickerDetailContent';

interface Props {
  selectedSymbol: string | null;
  setSelectedSymbol: (sym: string | null) => void;
  onOpenTrading?: (symbol: string) => void;
  /** Live watchlist ranks from App's useWatchlist poll — used for the side-panel strip. */
  watchlistEntries?: WatchlistEntry[];
  /** Scanner discovery provider for the Data sources panel. */
  discoveryProvider?: string;
  /** Alpaca IEX/SIP tier for the Data sources panel. */
  alpacaFeed?: string;
}

export function SidePanel({
  selectedSymbol,
  setSelectedSymbol,
  onOpenTrading,
  watchlistEntries = [],
  discoveryProvider,
  alpacaFeed,
}: Props) {
  const [input, setInput] = useState(selectedSymbol ?? '');
  const { detail, loading, refreshing, fetchFailed } = useTickerStream(selectedSymbol);
  const ibkrStatus = useIbkrStatus();

  const watchlistEntry = useMemo(() => {
    if (!selectedSymbol) return null;
    return watchlistEntries.find(e => e.symbol === selectedSymbol) ?? null;
  }, [selectedSymbol, watchlistEntries]);

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

  return (
    <aside className="side-panel">
      <div className="side-panel-search">
        <form className="side-search-form" onSubmit={handleSubmit}>
          <input
            className="side-search-input"
            type="text"
            value={input}
            onChange={e => setInput(e.target.value.toUpperCase())}
            placeholder="Symbol, e.g. AAPL"
            autoComplete="off"
            spellCheck={false}
            aria-label="Look up symbol"
          />
          <button type="submit" className="side-search-btn">Look Up</button>
        </form>
        {selectedSymbol && onOpenTrading && (
          <button
            type="button"
            className="side-open-trading-btn"
            onClick={() => onOpenTrading(selectedSymbol)}
            title={STOCK_VIEW_OPEN_TITLE}
          >
            {STOCK_VIEW_OPEN_LABEL}
          </button>
        )}
      </div>
      <div className="side-panel-body">
        <div className="quote-panel-title" title="Scanner sidebar quote — same data as Stock View">
          {QUOTE_PANEL_TITLE}
        </div>
        {showFullSpinner && (
          <div className="detail-loading">
            <div className="detail-loading-spinner" />
            <span>Loading…</span>
          </div>
        )}
        {!showFullSpinner && selectedSymbol && refreshing && detail && (
          <div className="detail-refreshing-bar">
            <div className="detail-loading-spinner detail-loading-spinner--small" />
            <span>Updating {selectedSymbol}…</span>
          </div>
        )}
        {!showFullSpinner && selectedSymbol && detail && (
          <div className="detail-body">
            <TickerDetailContent
              detail={detail}
              showChart
              layout="columns"
              watchlistEntry={watchlistEntry}
              ibkrConnected={ibkrStatus.connected}
              discoveryProvider={discoveryProvider}
              alpacaFeed={alpacaFeed}
            />
          </div>
        )}
        {!showFullSpinner && fetchFailed && !detail && selectedSymbol && (
          <div className="detail-empty">No data found for {selectedSymbol}.</div>
        )}
        {!showFullSpinner && !selectedSymbol && (
          <div className="detail-empty">Enter a ticker symbol above to look up a stock quote.</div>
        )}
      </div>
    </aside>
  );
}
