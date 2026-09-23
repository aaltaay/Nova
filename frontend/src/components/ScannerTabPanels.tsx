/**
 * Gappers / Gainers / Losers / After Hours / Catalysts tab bodies.
 * Gainers and Losers are separate registry modules sharing ScannerTable (Phase 4).
 */
import { useMemo, useState, type ReactNode } from 'react';
import { CatalystsTable } from './CatalystsTable';
import { EmptyState } from './EmptyState';
import { ScannerTable } from './ScannerTable';
import { type ScannerTableMeta } from '../hooks/useScannerPriceStream';
import { pinFirst, usePinnedRows } from '../scanner/pinnedRowsStore';
import { historyTableLoadError, tableHonestyLabel } from '../scanner/scannerHonesty';
import type { HistoryTableKey } from '../scanner/scannerHistory';
import { useLiveScannerFeedOptional } from '../scanner/ScannerDataContext';
import { LEADERBOARD_CATALYSTS_NOT_RECORDED } from '../leaderboard/leaderboardConstants';
import { replayListAbsence } from '../leaderboard/leaderboardRows';
import { LARGE_CAP_COLUMNS, SCANNER_COLUMNS } from '../constants';
import type { Afterhours, Gapper, Mover, ScannerRow, SortConfig } from '../types/scanner';
import type { Catalyst } from '../types/catalyst';
import type { HealthStatus } from '../types/health';
import type { MarketMode } from '../types/market';
import { sortedArray, toggleSort } from '../utils/sortRows';
import { useWatchlistOverlay } from '../strategy/useWatchlistOverlay';
import type { WatchlistEntry } from '../strategy/types';

/** Stable empty overlay for a history view (keeps useWatchlistOverlay's memo). */
const NO_WATCHLIST_ENTRIES: WatchlistEntry[] = [];

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
  /** When set, hide live freeze chrome and live empty-state copy. */
  historyDate?: string | null;
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
  historyDate = null,
}: Props) {
  const live = useLiveScannerFeedOptional();
  // Sim playback (ADR 022) is a past board like a history date: no live freeze chrome, no grading.
  const replay = live?.replay ?? null;
  const honestyBadge =
    !historyDate && !replay && activeTab !== 'catalysts'
      ? tableHonestyLabel(tableMeta[activeTab], live?.lastGood?.[activeTab])
      : null;
  const emptyHonesty =
    live?.feedError
    || (tableMeta[activeTab]?.state === 'unavailable' ? 'Unavailable -- no live roster' : null);
  const feedFailure = live?.restError ?? null;
  // History view: a table whose snapshot request failed says so (QA C51).
  const historyErrorFor = (table: HistoryTableKey, label: string): string | null =>
    live?.historyError
    ?? (historyDate && live?.historyFailed?.includes(table) ? historyTableLoadError(historyDate, label) : null);
  // Every table's empty state shares these; each adds its context, label and history error.
  const emptyShared = { health, discoveryProvider, historyDate, honestyHint: emptyHonesty, feedFailure };
  const emptyFor = (table: HistoryTableKey, label: string) => ({
    ...emptyShared,
    historyError: historyErrorFor(table, label),
    replayAbsence: replay ? replayListAbsence(replay, table) : null,
  });
  const [gapperSort, setGapperSort] = useState<SortConfig>({ key: '', dir: null });
  const [gainerSort, setGainerSort] = useState<SortConfig>({ key: '', dir: null });
  const [loserSort, setLoserSort] = useState<SortConfig>({ key: '', dir: null });
  const [afterhoursSort, setAfterhoursSort] = useState<SortConfig>({ key: '', dir: null });
  // Default sort RVOL descending -- "unusual volume first" (ADR 014 user decision).
  const [largeCapSort, setLargeCapSort] = useState<SortConfig>({ key: 'rvol', dir: 'desc' });
  const [catalystSort, setCatalystSort] = useState<SortConfig>({ key: '', dir: null });

  // The watchlist grades today's rows: a past snapshot is not graded, so its
  // WATCH column is a dash rather than today's score on an old row (QA W14).
  const gradedEntries = historyDate || replay ? NO_WATCHLIST_ENTRIES : watchlistEntries;
  const gappersWithWatchlist = useWatchlistOverlay(gappers, gradedEntries);
  const gainersWithWatchlist = useWatchlistOverlay(gainers, gradedEntries);
  const losersWithWatchlist = useWatchlistOverlay(losers, gradedEntries);
  const afterhoursWithWatchlist = useWatchlistOverlay(afterhours, gradedEntries);

  // Pinned rows lead every list for the session, after the sort.
  const pinned = usePinnedRows();
  const sortedGappers = useMemo(
    () => pinFirst(sortedArray(gappersWithWatchlist, gapperSort), pinned),
    [gappersWithWatchlist, gapperSort, pinned],
  );
  const sortedGainers = useMemo(
    () => pinFirst(sortedArray(gainersWithWatchlist, gainerSort), pinned),
    [gainersWithWatchlist, gainerSort, pinned],
  );
  const sortedLosers = useMemo(
    () => pinFirst(sortedArray(losersWithWatchlist, loserSort), pinned),
    [losersWithWatchlist, loserSort, pinned],
  );
  const sortedAfterhours = useMemo(
    () => pinFirst(sortedArray(afterhoursWithWatchlist, afterhoursSort), pinned),
    [afterhoursWithWatchlist, afterhoursSort, pinned],
  );
  // No watchlist overlay -- Five Pillars scoring (price $2-$20, float <20M) is a
  // day-trade fit test that does not apply to a large-cap swing table.
  const sortedLargeCap = useMemo(
    () => pinFirst(sortedArray(largeCap, largeCapSort), pinned),
    [largeCap, largeCapSort, pinned],
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
        {...emptyFor('gappers', 'gappers')}
        context={mode === 'market' ? 'premarket' : mode}
        emptyLabel="gappers"
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
        fetchError={replay ? LEADERBOARD_CATALYSTS_NOT_RECORDED : live?.catalystsError}
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
        {...emptyFor('gainers', 'gainers')}
        context={mode === 'premarket' ? 'market' : mode}
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
        {...emptyFor('losers', 'losers')}
        context={mode === 'premarket' ? 'market' : mode}
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
            {...emptyFor('afterhours', 'after-hours movers')}
            context={mode === 'market' ? 'afterhours' : mode}
            emptyLabel="after-hours movers"
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
        {...emptyFor('large_cap', 'large cap movers')}
        context={mode === 'market' ? 'market' : mode}
        emptyLabel="large cap movers"
      />
    );
  }

  return (
    <>
      {honestyBadge && (
        <div
          className={
            honestyBadge.kind === 'frozen'
              ? 'scanner-frozen-badge'
              : 'scanner-frozen-badge scanner-honesty-badge'
          }
          role="status"
          title={
            honestyBadge.kind === 'frozen'
              ? 'This table is immutable for the rest of the session (ADR 008)'
              : honestyBadge.text
          }
        >
          {honestyBadge.text}
        </div>
      )}
      {panel}
    </>
  );
}
