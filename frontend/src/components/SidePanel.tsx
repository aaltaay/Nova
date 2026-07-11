/** Scanner side panel — quote, panel chart, fundamentals for selectedSymbol. */
import { useEffect, useState } from 'react';
import { useTickerStream } from '../hooks/useTickerStream';
import { TickerDetailContent } from './TickerDetailContent';

interface Props {
  selectedSymbol: string | null;
  setSelectedSymbol: (sym: string | null) => void;
  onOpenTrading?: (symbol: string) => void;
}

export function SidePanel({ selectedSymbol, setSelectedSymbol, onOpenTrading }: Props) {
  const [input, setInput] = useState(selectedSymbol ?? '');
  const { detail, loading, refreshing, fetchFailed } = useTickerStream(selectedSymbol);

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
            title="Open full trading view (same as double-clicking the symbol)"
          >
            Full view
          </button>
        )}
      </div>
      <div className="side-panel-body">
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
            <TickerDetailContent detail={detail} showChart />
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
