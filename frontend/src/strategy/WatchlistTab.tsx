/** Watchlist tab — Five Pillars ranked table + live setup Signals sub-panel. Signal-only; no orders placed. */
import { useState } from 'react';
import { WATCHLIST_SUBSCORE_LABELS } from '../constants';
import { SignalsPanel } from './SignalsPanel';
import { useSignalsStream } from './useSignalsStream';
import type { WatchlistEntry } from './types';

function fmtScore(v: number): string {
  return v.toFixed(0);
}

function PillarChips({ pillars }: { pillars: WatchlistEntry['five_pillars']['pillars'] }) {
  return (
    <span className="pillar-chip-row">
      {pillars.map(p => (
        <span
          key={p.name}
          className={`pillar-chip ${p.passed ? 'pillar-pass' : 'pillar-fail'}`}
          title={p.detail}
        >
          {p.passed ? '\u2713' : '\u2717'} {p.name.replace('_', ' ')}
        </span>
      ))}
    </span>
  );
}

function WatchlistRow({
  entry,
  selected,
  onSelect,
}: {
  entry: WatchlistEntry;
  selected: boolean;
  onSelect: (symbol: string) => void;
}) {
  return (
    <tr className={selected ? 'row-selected' : ''}>
      <td>
        <button
          className={`symbol-btn${selected ? ' active' : ''}`}
          onClick={() => onSelect(entry.symbol)}
        >
          {entry.symbol}
        </button>
      </td>
      <td>
        <span className={entry.five_pillars.all_pass ? 'positive' : 'na-muted'}>
          {entry.five_pillars.checkmark}
        </span>
      </td>
      <td><PillarChips pillars={entry.five_pillars.pillars} /></td>
      {Object.keys(WATCHLIST_SUBSCORE_LABELS).map(key => (
        <td key={key}>{fmtScore(entry.sub_scores[key as keyof typeof entry.sub_scores])}</td>
      ))}
      <td className="watchlist-composite-cell">{fmtScore(entry.composite_score)}</td>
    </tr>
  );
}

interface WatchlistTabProps {
  entries: WatchlistEntry[];
  loading: boolean;
  error: string | null;
  selectedSymbol: string | null;
  onSelectSymbol: (symbol: string) => void;
}

type WatchlistSubTab = 'watchlist' | 'signals';

export function WatchlistTab({ entries, loading, error, selectedSymbol, onSelectSymbol }: WatchlistTabProps) {
  const [subTab, setSubTab] = useState<WatchlistSubTab>('watchlist');
  const signalsStream = useSignalsStream();

  return (
    <div className="watchlist-tab">
      <div className="sub-tab-bar">
        <button
          className={`sub-tab ${subTab === 'watchlist' ? 'active' : ''}`}
          onClick={() => setSubTab('watchlist')}
        >
          Watchlist
          {entries.length > 0 && <span className="tab-count">{entries.length}</span>}
        </button>
        <button
          className={`sub-tab ${subTab === 'signals' ? 'active' : ''}`}
          onClick={() => setSubTab('signals')}
        >
          Signals
          {signalsStream.signals.length > 0 && <span className="tab-count">{signalsStream.signals.length}</span>}
        </button>
      </div>

      {subTab === 'watchlist' && (
        <>
          <div className="watchlist-description">
            Ranked by the Five Pillars (price, % change, relative volume, catalyst, float) with a
            composite score breaking ties. Signal only — no orders are placed from this tab.
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
                    <th>Symbol</th>
                    <th>Pillars</th>
                    <th>Detail</th>
                    {Object.values(WATCHLIST_SUBSCORE_LABELS).map(label => (
                      <th key={label}>{label}</th>
                    ))}
                    <th>Score</th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map(entry => (
                    <WatchlistRow
                      key={entry.symbol}
                      entry={entry}
                      selected={selectedSymbol === entry.symbol}
                      onSelect={onSelectSymbol}
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
        />
      )}
    </div>
  );
}
