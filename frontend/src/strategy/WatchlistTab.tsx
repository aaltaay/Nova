/** Watchlist tab — Five Pillars ranked table, the live Setups scanner, the Journal and the Backtest. Signal-only; no orders placed. */
import { lazy, Suspense, useState } from 'react';
import { SelectableTableRow } from '../components/SelectableTableRow';
import { ScannerRowNumCell, ScannerRowNumHeader } from '../components/ScannerTable';
import { SymbolSelectButton } from '../components/SymbolSelectButton';
import { TabLazyFallback } from '../components/TabLazyFallback';
import { WATCHLIST_SUBSCORE_LABELS, WATCHLIST_SUBSCORE_TOOLTIPS } from '../constants';

const BacktestPanel = lazy(() =>
  import('./BacktestPanel').then(m => ({ default: m.BacktestPanel })),
);
import { JournalPanel } from './JournalPanel';
import { PillarChips } from './PillarChips';
import { SetupsPanel } from '../setups/SetupsPanel';
import { SetupsTabCount } from '../setups/SetupsTabCount';
import type { WatchlistEntry } from './types';

function fmtScore(v: number): string {
  return v.toFixed(0);
}

function WatchlistRow({
  entry,
  index,
  selected,
  onSelect,
  onOpenTrading,
}: {
  entry: WatchlistEntry;
  index: number;
  selected: boolean;
  onSelect: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
}) {
  return (
    <SelectableTableRow
      symbol={entry.symbol}
      selected={selected}
      onSelect={onSelect}
      onOpenTrading={onOpenTrading}
      openOnRowClick={false}
    >
      <ScannerRowNumCell index={index} />
      <td>
        <SymbolSelectButton
          symbol={entry.symbol}
          selected={selected}
          onSelect={onSelect}
          onOpenTrading={onOpenTrading}
        />
      </td>
      <td>
        <span
          className={entry.five_pillars.all_pass ? 'positive' : 'na-muted'}
          title={`${entry.five_pillars.pass_count} of ${entry.five_pillars.total} pillars pass`}
        >
          {entry.five_pillars.checkmark}
        </span>
      </td>
      <td><PillarChips pillars={entry.five_pillars.pillars} /></td>
      {Object.keys(WATCHLIST_SUBSCORE_LABELS).map(key => (
        <td key={key}>{fmtScore(entry.sub_scores[key as keyof typeof entry.sub_scores])}</td>
      ))}
      <td className="watchlist-composite-cell">{fmtScore(entry.composite_score)}</td>
    </SelectableTableRow>
  );
}

interface WatchlistTabProps {
  entries: WatchlistEntry[];
  loading: boolean;
  error: string | null;
  selectedSymbol: string | null;
  onSelectSymbol: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
}

type WatchlistSubTab = 'watchlist' | 'setups' | 'journal' | 'backtest';

export function WatchlistTab({
  entries, loading, error, selectedSymbol, onSelectSymbol, onOpenTrading,
}: WatchlistTabProps) {
  const [subTab, setSubTab] = useState<WatchlistSubTab>('watchlist');

  return (
    <div className="watchlist-tab">
      <div className="sub-tab-bar">
        <button
          className={`sub-tab ${subTab === 'watchlist' ? 'active' : ''}`}
          onClick={() => setSubTab('watchlist')}
          title="Every gapper/gainer scored against the Five Pillars and ranked by composite score. Refreshes continuously. No orders are placed."
        >
          Watchlist
          {entries.length > 0 && <span className="tab-count">{entries.length}</span>}
        </button>
        <button
          className={`sub-tab ${subTab === 'setups' ? 'active' : ''}`}
          onClick={() => setSubTab('setups')}
          title="Live first-pullback scanner: leg up, armed, near the trigger, triggered or failed, with the bot's read of the tape. It proposes; it never places."
        >
          Setups
          <SetupsTabCount />
        </button>
        <button
          className={`sub-tab ${subTab === 'journal' ? 'active' : ''}`}
          onClick={() => setSubTab('journal')}
          title="Trade log, win-rate/profit-loss metrics, today's risk state, and the live-money go/no-go bar. Includes an optional 'Show demo data' toggle for testing before real trades exist."
        >
          Journal
        </button>
        <button
          className={`sub-tab ${subTab === 'backtest' ? 'active' : ''}`}
          onClick={() => setSubTab('backtest')}
          title="Run Nova-native backtest on archived 1m bars. Metrics only — no orders."
        >
          Backtest
        </button>
      </div>

      {subTab === 'watchlist' && (
        <>
          <div className="watchlist-description">
            Ranked by the Five Pillars (price, % change, relative volume, catalyst, float) with a
            composite score breaking ties. Signal only — no orders are placed from this tab.
            Click a row for the Quote Panel; click the ticker to open Trader.
          </div>
          {error && <div className="empty-state">{error}</div>}
          {!error && entries.length === 0 ? (
            <div className="empty-state">
              {loading ? 'Loading watchlist\u2026' : 'No candidates currently meet scanning criteria.'}
            </div>
          ) : (
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <ScannerRowNumHeader />
                    <th title="Click the row for the Quote Panel. Click the ticker to open Trader.">Symbol</th>
                    <th title="How many of the 5 Pillars (price, % change, relative volume, catalyst, float) currently pass. All 5 passing ranks a symbol above any partial match.">Pillars</th>
                    <th title="Hover a chip above to see exactly why that pillar passed or failed for this symbol.">Detail</th>
                    {Object.entries(WATCHLIST_SUBSCORE_LABELS).map(([key, label]) => (
                      <th key={label} title={WATCHLIST_SUBSCORE_TOOLTIPS[key] ?? label}>{label}</th>
                    ))}
                    <th title="Weighted 0-100 composite of the 4 sub-scores to the left — breaks ties among symbols with the same pillar pass count.">Score</th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map((entry, index) => (
                    <WatchlistRow
                      key={entry.symbol}
                      entry={entry}
                      index={index}
                      selected={selectedSymbol === entry.symbol}
                      onSelect={onSelectSymbol}
                      onOpenTrading={onOpenTrading}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {subTab === 'setups' && (
        <SetupsPanel
          selectedSymbol={selectedSymbol}
          onSelectSymbol={onSelectSymbol}
          onOpenTrading={onOpenTrading}
        />
      )}

      {subTab === 'journal' && (
        <JournalPanel
          active={subTab === 'journal'}
          selectedSymbol={selectedSymbol}
          onSelectSymbol={onSelectSymbol}
          onOpenTrading={onOpenTrading}
        />
      )}

      {subTab === 'backtest' && (
        <Suspense fallback={<TabLazyFallback />}>
          <BacktestPanel active={subTab === 'backtest'} />
        </Suspense>
      )}
    </div>
  );
}
