/**
 * Gappers / Movers / After Hours / Catalysts tab bodies.
 * Extracted from App.tsx — keeps DashboardPage under the component size limit.
 */
import { useMemo, useState } from 'react';
import { CatalystsTable } from './CatalystsTable';
import { EmptyState } from './EmptyState';
import { ScannerTable } from './ScannerTable';
import { SMALL_CAP_MAX, SMALL_CAP_MIN, SCANNER_COLUMNS } from '../constants';
import type { Afterhours, Gapper, Mover, SortConfig } from '../types/scanner';
import type { Catalyst } from '../types/catalyst';
import type { HealthStatus } from '../types/health';
import type { MarketMode } from './AppHeader';
import { sortedArray, toggleSort } from '../utils/sortRows';
import { useWatchlistOverlay } from '../strategy/useWatchlistOverlay';
import type { WatchlistEntry } from '../strategy/types';

interface Props {
  activeTab: 'gappers' | 'movers' | 'afterhours' | 'catalysts';
  mode: MarketMode;
  health: HealthStatus;
  discoveryProvider: string;
  gappers: Gapper[];
  gainers: Mover[];
  losers: Mover[];
  afterhours: Afterhours[];
  catalysts: Catalyst[];
  watchlistEntries: WatchlistEntry[];
  selectedSymbol: string | null;
  onSelect: (sym: string) => void;
  onOpenTrading: (sym: string) => void;
  pricesStale: boolean;
  flashSymbols: Record<string, 'up' | 'down'>;
}

export function ScannerTabPanels({
  activeTab,
  mode,
  health,
  discoveryProvider,
  gappers,
  gainers,
  losers,
  afterhours,
  catalysts,
  watchlistEntries,
  selectedSymbol,
  onSelect,
  onOpenTrading,
  pricesStale,
  flashSymbols,
}: Props) {
  const [gapperSubTab, setGapperSubTab] = useState<'all' | 'small_cap'>('all');
  const [moverSubTab, setMoverSubTab] = useState<'gainers' | 'losers'>('gainers');
  const [gapperSort, setGapperSort] = useState<SortConfig>({ key: '', dir: null });
  const [moverSort, setMoverSort] = useState<SortConfig>({ key: '', dir: null });
  const [afterhoursSort, setAfterhoursSort] = useState<SortConfig>({ key: '', dir: null });
  const [catalystSort, setCatalystSort] = useState<SortConfig>({ key: '', dir: null });

  const gappersWithWatchlist = useWatchlistOverlay(gappers, watchlistEntries);
  const gainersWithWatchlist = useWatchlistOverlay(gainers, watchlistEntries);
  const losersWithWatchlist = useWatchlistOverlay(losers, watchlistEntries);
  const afterhoursWithWatchlist = useWatchlistOverlay(afterhours, watchlistEntries);

  const smallCapGappers = useMemo(
    () =>
      gappersWithWatchlist.filter(
        g =>
          g.market_cap != null &&
          g.market_cap >= SMALL_CAP_MIN &&
          g.market_cap < SMALL_CAP_MAX,
      ),
    [gappersWithWatchlist],
  );

  const sortedGappers = useMemo(
    () => sortedArray(gappersWithWatchlist, gapperSort),
    [gappersWithWatchlist, gapperSort],
  );
  const sortedSmallCapGappers = useMemo(
    () => sortedArray(smallCapGappers, gapperSort),
    [smallCapGappers, gapperSort],
  );
  const sortedGainers = useMemo(
    () => sortedArray(gainersWithWatchlist, moverSort),
    [gainersWithWatchlist, moverSort],
  );
  const sortedLosers = useMemo(
    () => sortedArray(losersWithWatchlist, moverSort),
    [losersWithWatchlist, moverSort],
  );
  const sortedAfterhours = useMemo(
    () => sortedArray(afterhoursWithWatchlist, afterhoursSort),
    [afterhoursWithWatchlist, afterhoursSort],
  );
  const sortedCatalysts = useMemo(
    () => sortedArray(catalysts, catalystSort),
    [catalysts, catalystSort],
  );

  if (activeTab === 'gappers') {
    return (
      <>
        <div className="sub-tab-bar">
          <button
            className={`sub-tab ${gapperSubTab === 'all' ? 'active' : ''}`}
            onClick={() => setGapperSubTab('all')}
          >
            All Gaps
            {gappers.length > 0 && <span className="tab-count">{gappers.length}</span>}
          </button>
          <button
            className={`sub-tab ${gapperSubTab === 'small_cap' ? 'active' : ''}`}
            onClick={() => setGapperSubTab('small_cap')}
          >
            Small Cap
            {smallCapGappers.length > 0 && (
              <span className="tab-count">{smallCapGappers.length}</span>
            )}
          </button>
        </div>
        {(gapperSubTab === 'all' ? gappers : smallCapGappers).length > 0 ? (
          <ScannerTable
            columns={SCANNER_COLUMNS}
            data={gapperSubTab === 'all' ? sortedGappers : sortedSmallCapGappers}
            sortState={gapperSort}
            onSort={key => toggleSort(gapperSort, setGapperSort, key)}
            selectedSymbol={selectedSymbol}
            onSelect={onSelect}
            onOpenTrading={onOpenTrading}
            pricesStale={pricesStale}
            flashSymbols={flashSymbols}
          />
        ) : (
          <EmptyState
            health={health}
            context={mode === 'market' ? 'premarket' : mode}
            discoveryProvider={discoveryProvider}
          />
        )}
      </>
    );
  }

  if (activeTab === 'catalysts') {
    return (
      <CatalystsTable
        catalysts={sortedCatalysts}
        sortState={catalystSort}
        onSort={key => toggleSort(catalystSort, setCatalystSort, key)}
        selectedSymbol={selectedSymbol}
        onSelect={onSelect}
        onOpenTrading={onOpenTrading}
        health={health}
      />
    );
  }

  if (activeTab === 'movers') {
    return (
      <>
        <div className="sub-tab-bar">
          <button
            className={`sub-tab ${moverSubTab === 'gainers' ? 'active' : ''}`}
            onClick={() => setMoverSubTab('gainers')}
          >
            Gainers
            {gainers.length > 0 && <span className="tab-count">{gainers.length}</span>}
          </button>
          <button
            className={`sub-tab ${moverSubTab === 'losers' ? 'active' : ''}`}
            onClick={() => setMoverSubTab('losers')}
          >
            Losers
            {losers.length > 0 && <span className="tab-count">{losers.length}</span>}
          </button>
        </div>
        {(moverSubTab === 'gainers' ? gainers : losers).length > 0 ? (
          <ScannerTable
            columns={SCANNER_COLUMNS}
            data={moverSubTab === 'gainers' ? sortedGainers : sortedLosers}
            sortState={moverSort}
            onSort={key => toggleSort(moverSort, setMoverSort, key)}
            selectedSymbol={selectedSymbol}
            onSelect={onSelect}
            onOpenTrading={onOpenTrading}
            pricesStale={pricesStale}
            flashSymbols={flashSymbols}
          />
        ) : (
          <EmptyState
            health={health}
            context={mode === 'premarket' ? 'market' : mode}
            discoveryProvider={discoveryProvider}
            emptyLabel={moverSubTab}
          />
        )}
      </>
    );
  }

  // afterhours
  return (
    <>
      {sortedAfterhours.length > 0 ? (
        <ScannerTable
          columns={SCANNER_COLUMNS}
          data={sortedAfterhours}
          sortState={afterhoursSort}
          onSort={key => toggleSort(afterhoursSort, setAfterhoursSort, key)}
          selectedSymbol={selectedSymbol}
          onSelect={onSelect}
          onOpenTrading={onOpenTrading}
          pricesStale={pricesStale}
          flashSymbols={flashSymbols}
        />
      ) : (
        <EmptyState
          health={health}
          context={mode === 'market' ? 'afterhours' : mode}
          discoveryProvider={discoveryProvider}
        />
      )}
    </>
  );
}
