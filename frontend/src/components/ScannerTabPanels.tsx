/**
 * Gappers / Gainers / Losers / After Hours / Catalysts tab bodies.
 * Gainers and Losers are separate registry modules sharing ScannerTable (Phase 4).
 */
import { useMemo, useState, type ReactNode } from 'react';
import { CatalystsTable } from './CatalystsTable';
import { EmptyState } from './EmptyState';
import { ScannerTable } from './ScannerTable';
import { HodMomoIntegrityBanner } from '../hod_momo/HodMomoIntegrityBanner';
import { frozenTableLabel, type ScannerTableMeta } from '../hooks/useScannerPriceStream';
import { SMALL_CAP_MAX, SMALL_CAP_MIN, SCANNER_COLUMNS } from '../constants';
import type { Afterhours, Gapper, Mover, SortConfig } from '../types/scanner';
import type { Catalyst } from '../types/catalyst';
import type { HealthStatus } from '../types/health';
import type { MarketMode } from './AppHeader';
import { sortedArray, toggleSort } from '../utils/sortRows';
import { useWatchlistOverlay } from '../strategy/useWatchlistOverlay';
import type { WatchlistEntry } from '../strategy/types';

interface Props {
  activeTab: 'gappers' | 'gainers' | 'losers' | 'afterhours' | 'catalysts';
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
  rowQuoteTs?: Record<string, number>;
  nowSec?: number;
  /** ADR 008 — per-table freeze/session metadata, keyed by table name. */
  tableMeta?: Record<string, ScannerTableMeta>;
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
  rowQuoteTs = {},
  nowSec = 0,
  tableMeta = {},
}: Props) {
  const frozenLabel =
    activeTab !== 'catalysts' ? frozenTableLabel(tableMeta[activeTab]) : null;
  const [gapperSubTab, setGapperSubTab] = useState<'all' | 'small_cap'>('all');
  const [gapperSort, setGapperSort] = useState<SortConfig>({ key: '', dir: null });
  const [gainerSort, setGainerSort] = useState<SortConfig>({ key: '', dir: null });
  const [loserSort, setLoserSort] = useState<SortConfig>({ key: '', dir: null });
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
    () => sortedArray(gainersWithWatchlist, gainerSort),
    [gainersWithWatchlist, gainerSort],
  );
  const sortedLosers = useMemo(
    () => sortedArray(losersWithWatchlist, loserSort),
    [losersWithWatchlist, loserSort],
  );
  const sortedAfterhours = useMemo(
    () => sortedArray(afterhoursWithWatchlist, afterhoursSort),
    [afterhoursWithWatchlist, afterhoursSort],
  );
  const sortedCatalysts = useMemo(
    () => sortedArray(catalysts, catalystSort),
    [catalysts, catalystSort],
  );

  let panel: ReactNode = null;

  if (activeTab === 'gappers') {
    panel = (
      <>
        <div className="sub-tab-bar">
          <button
            type="button"
            className={`sub-tab ${gapperSubTab === 'all' ? 'active' : ''}`}
            onClick={() => setGapperSubTab('all')}
          >
            All Gaps
            {gappers.length > 0 && <span className="tab-count">{gappers.length}</span>}
          </button>
          <button
            type="button"
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
            rowQuoteTs={rowQuoteTs}
            nowSec={nowSec}
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
  } else if (activeTab === 'catalysts') {
    panel = (
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
  } else if (activeTab === 'gainers') {
    panel = gainers.length > 0 ? (
      <ScannerTable
        columns={SCANNER_COLUMNS}
        data={sortedGainers}
        sortState={gainerSort}
        onSort={key => toggleSort(gainerSort, setGainerSort, key)}
        selectedSymbol={selectedSymbol}
        onSelect={onSelect}
        onOpenTrading={onOpenTrading}
        pricesStale={pricesStale}
        flashSymbols={flashSymbols}
        rowQuoteTs={rowQuoteTs}
        nowSec={nowSec}
      />
    ) : (
      <EmptyState
        health={health}
        context={mode === 'premarket' ? 'market' : mode}
        discoveryProvider={discoveryProvider}
        emptyLabel="gainers"
      />
    );
  } else if (activeTab === 'losers') {
    panel = losers.length > 0 ? (
      <ScannerTable
        columns={SCANNER_COLUMNS}
        data={sortedLosers}
        sortState={loserSort}
        onSort={key => toggleSort(loserSort, setLoserSort, key)}
        selectedSymbol={selectedSymbol}
        onSelect={onSelect}
        onOpenTrading={onOpenTrading}
        pricesStale={pricesStale}
        flashSymbols={flashSymbols}
        rowQuoteTs={rowQuoteTs}
        nowSec={nowSec}
      />
    ) : (
      <EmptyState
        health={health}
        context={mode === 'premarket' ? 'market' : mode}
        discoveryProvider={discoveryProvider}
        emptyLabel="losers"
      />
    );
  } else {
    // afterhours
    panel = (
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
            rowQuoteTs={rowQuoteTs}
            nowSec={nowSec}
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

  return (
    <>
      <HodMomoIntegrityBanner />
      {frozenLabel && (
        <div
          className="scanner-frozen-badge"
          role="status"
          title="This table is immutable for the rest of the session (ADR 008)"
        >
          {frozenLabel}
        </div>
      )}
      {panel}
    </>
  );
}
