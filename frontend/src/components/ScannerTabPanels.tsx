/**
 * Gappers / Gainers / Losers / After Hours / Catalysts tab bodies.
 * Gainers and Losers are separate registry modules sharing ScannerTable (Phase 4).
 */
import { useMemo, useState, type ReactNode } from 'react';
import { CatalystsTable } from './CatalystsTable';
import { EmptyState } from './EmptyState';
import { ScannerTable } from './ScannerTable';
import { frozenTableLabel, type ScannerTableMeta } from '../hooks/useScannerPriceStream';
import { LARGE_CAP_COLUMNS, SCANNER_COLUMNS } from '../constants';
import type { Afterhours, Gapper, Mover, ScannerRow, SortConfig } from '../types/scanner';
import type { Catalyst } from '../types/catalyst';
import type { HealthStatus } from '../types/health';
import type { MarketMode } from './AppHeader';
import { sortedArray, toggleSort } from '../utils/sortRows';
import { useWatchlistOverlay } from '../strategy/useWatchlistOverlay';
import type { WatchlistEntry } from '../strategy/types';

interface Props {
  activeTab: 'gappers' | 'gainers' | 'losers' | 'afterhours' | 'large_cap' | 'catalysts';
  mode: MarketMode;
  health: HealthStatus;
  discoveryProvider: string;
  gappers: Gapper[];
  gainers: Mover[];
  losers: Mover[];
  afterhours: Afterhours[];
  /** Large Cap swing table (ADR 014) — always-live, never freezes. */
  largeCap: ScannerRow[];
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
  largeCap,
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
  const [gapperSort, setGapperSort] = useState<SortConfig>({ key: '', dir: null });
  const [gainerSort, setGainerSort] = useState<SortConfig>({ key: '', dir: null });
  const [loserSort, setLoserSort] = useState<SortConfig>({ key: '', dir: null });
  const [afterhoursSort, setAfterhoursSort] = useState<SortConfig>({ key: '', dir: null });
  // Default sort RVOL descending -- "unusual volume first" (ADR 014 user decision).
  const [largeCapSort, setLargeCapSort] = useState<SortConfig>({ key: 'rvol', dir: 'desc' });
  const [catalystSort, setCatalystSort] = useState<SortConfig>({ key: '', dir: null });

  const gappersWithWatchlist = useWatchlistOverlay(gappers, watchlistEntries);
  const gainersWithWatchlist = useWatchlistOverlay(gainers, watchlistEntries);
  const losersWithWatchlist = useWatchlistOverlay(losers, watchlistEntries);
  const afterhoursWithWatchlist = useWatchlistOverlay(afterhours, watchlistEntries);

  const sortedGappers = useMemo(
    () => sortedArray(gappersWithWatchlist, gapperSort),
    [gappersWithWatchlist, gapperSort],
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
  // No watchlist overlay -- Five Pillars scoring (price $2-$20, float <20M) is a
  // day-trade fit test that does not apply to a large-cap swing table.
  const sortedLargeCap = useMemo(
    () => sortedArray(largeCap, largeCapSort),
    [largeCap, largeCapSort],
  );
  const sortedCatalysts = useMemo(
    () => sortedArray(catalysts, catalystSort),
    [catalysts, catalystSort],
  );

  let panel: ReactNode = null;

  if (activeTab === 'gappers') {
    panel = gappers.length > 0 ? (
      <ScannerTable
        columns={SCANNER_COLUMNS}
        data={sortedGappers}
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
  } else if (activeTab === 'afterhours') {
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
  } else {
    // large_cap (ADR 014) — always-live, never freezes, so an empty list here
    // means the IB lease hasn't hydrated yet, not a quiet market.
    panel = sortedLargeCap.length > 0 ? (
      <ScannerTable
        columns={LARGE_CAP_COLUMNS}
        data={sortedLargeCap}
        sortState={largeCapSort}
        onSort={key => toggleSort(largeCapSort, setLargeCapSort, key)}
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
        context={mode === 'market' ? 'market' : mode}
        discoveryProvider={discoveryProvider}
        emptyLabel="large cap movers"
      />
    );
  }

  return (
    <>
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
