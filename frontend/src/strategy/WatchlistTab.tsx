/** Watchlist tab — Five Pillars ranked table + live setup Signals + Nova OS Decision audit. Signal-only; no orders placed. */
import { useState } from 'react';
import { SelectableTableRow } from '../components/SelectableTableRow';
import { SymbolSelectButton } from '../components/SymbolSelectButton';
import { WATCHLIST_SUBSCORE_LABELS, WATCHLIST_SUBSCORE_TOOLTIPS } from '../constants';
import { ArchiveRewind } from './ArchiveRewind';
import { BacktestPanel } from './BacktestPanel';
import { DecisionPanel } from './DecisionPanel';
import { ExecutorPanel } from './ExecutorPanel';
import { JournalPanel } from './JournalPanel';
import { PillarChips } from './PillarChips';
import { SignalsPanel } from './SignalsPanel';
import { useSignalsStream } from './useSignalsStream';
import type { WatchlistEntry } from './types';

function fmtScore(v: number): string {
  return v.toFixed(0);
}

function WatchlistRow({
  entry,
  selected,
  onSelect,
  onOpenTrading,
}: {
  entry: WatchlistEntry;
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
    >
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

type WatchlistSubTab = 'watchlist' | 'signals' | 'decision' | 'journal' | 'automation' | 'archive' | 'backtest';

export function WatchlistTab({
  entries, loading, error, selectedSymbol, onSelectSymbol, onOpenTrading,
}: WatchlistTabProps) {
  const [subTab, setSubTab] = useState<WatchlistSubTab>('watchlist');
  const signalsStream = useSignalsStream();

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
          className={`sub-tab ${subTab === 'signals' ? 'active' : ''}`}
          onClick={() => setSubTab('signals')}
          title="Live feed of Gap and Go / Bull Flag / ABCD triggers as the background scanner finds them. No orders are placed."
        >
          Signals
          {signalsStream.signals.length > 0 && <span className="tab-count">{signalsStream.signals.length}</span>}
        </button>
        <button
          className={`sub-tab ${subTab === 'decision' ? 'active' : ''}`}
          onClick={() => setSubTab('decision')}
          title="Nova OS gate-by-gate BUY / WAIT / NO BUY audit for top watchlist names. Signal only — nothing is placed."
        >
          Decision
        </button>
        <button
          className={`sub-tab ${subTab === 'journal' ? 'active' : ''}`}
          onClick={() => setSubTab('journal')}
          title="Trade log, win-rate/profit-loss metrics, today's risk state, and the live-money go/no-go bar. Includes an optional 'Show demo data' toggle for testing before real trades exist."
        >
          Journal
        </button>
        <button
          className={`sub-tab ${subTab === 'automation' ? 'active' : ''}`}
          onClick={() => setSubTab('automation')}
          title="Control mode ladder (signal/confirm/auto_paper/auto_live) for automated paper bracket orders on IBKR, plus the kill switch. Starts at signal by default and on every backend restart."
        >
          Automation
        </button>
        <button
          className={`sub-tab ${subTab === 'archive' ? 'active' : ''}`}
          onClick={() => setSubTab('archive')}
          title="Local cold-archive days and decide(record=False) replay (Nova OS P9). No orders."
        >
          Archive
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
            Click a symbol for the side panel; double-click for the full trading view.
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
                    <th title="Click: side panel. Double-click: full trading view.">Symbol</th>
                    <th title="How many of the 5 Pillars (price, % change, relative volume, catalyst, float) currently pass. All 5 passing ranks a symbol above any partial match.">Pillars</th>
                    <th title="Hover a chip above to see exactly why that pillar passed or failed for this symbol.">Detail</th>
                    {Object.entries(WATCHLIST_SUBSCORE_LABELS).map(([key, label]) => (
                      <th key={label} title={WATCHLIST_SUBSCORE_TOOLTIPS[key] ?? label}>{label}</th>
                    ))}
                    <th title="Weighted 0-100 composite of the 4 sub-scores to the left — breaks ties among symbols with the same pillar pass count.">Score</th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map(entry => (
                    <WatchlistRow
                      key={entry.symbol}
                      entry={entry}
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

      {subTab === 'signals' && (
        <SignalsPanel
          signals={signalsStream.signals}
          connected={signalsStream.connected}
          selectedSymbol={selectedSymbol}
          onSelectSymbol={onSelectSymbol}
          onOpenTrading={onOpenTrading}
        />
      )}

      {subTab === 'decision' && (
        <DecisionPanel
          active={subTab === 'decision'}
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

      {subTab === 'automation' && (
        <ExecutorPanel
          active={subTab === 'automation'}
          selectedSymbol={selectedSymbol}
          onSelectSymbol={onSelectSymbol}
          onOpenTrading={onOpenTrading}
        />
      )}

      {subTab === 'archive' && <ArchiveRewind active={subTab === 'archive'} />}

      {subTab === 'backtest' && <BacktestPanel active={subTab === 'backtest'} />}
    </div>
  );
}
