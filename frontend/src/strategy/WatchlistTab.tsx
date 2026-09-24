/** Contenders tab (id `watchlist`) — what's worth trading (Five Pillars, market facts, catalyst, setup
 * state, bot allowlist), the live Setups scanner, the Journal and the Backtest. Signal-only; no orders
 * placed. Named Contenders 2026-09-23 so "Watch list" means the operator's hand-picked list (watch_list/). */
import { lazy, Suspense, useState } from 'react';
import { TabLazyFallback } from '../components/TabLazyFallback';

const BacktestPanel = lazy(() =>
  import('./BacktestPanel').then(m => ({ default: m.BacktestPanel })),
);
import { JournalPanel } from './JournalPanel';
import { SetupsPanel } from '../setups/SetupsPanel';
import { SetupsTabCount } from '../setups/SetupsTabCount';
import { WatchlistTable } from './WatchlistTable';
import type { WatchlistEntry } from './types';

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
          title="Contenders: every gapper/gainer scored against the Five Pillars and ranked by composite score. Refreshes continuously. No orders are placed. (Your own hand-picked symbols are the Watch list.)"
        >
          Contenders
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
        <WatchlistTable
          entries={entries}
          loading={loading}
          error={error}
          selectedSymbol={selectedSymbol}
          onSelectSymbol={onSelectSymbol}
          onOpenTrading={onOpenTrading}
        />
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
