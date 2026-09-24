/**
 * Renders the active tab body via registry id lookup (Phase 4).
 * Keeps DashboardPage under the component size limit.
 * HOD Momo / Running Up live in the AppShell dock — not hosted here; Bots is a
 * shell page (pages/NavPageHost), never a dashboard tab.
 */
import { lazy, Suspense } from 'react';
import { ScannerTabPanels } from './ScannerTabPanels';
import { TabLazyFallback } from './TabLazyFallback';
import { getModule, type ActiveTab } from '../workspace/registry';

const TradingTab = lazy(() =>
  import('../ibkr/TradingTab').then(m => ({ default: m.TradingTab })),
);
const WatchlistTab = lazy(() =>
  import('../strategy/WatchlistTab').then(m => ({ default: m.WatchlistTab })),
);
const WatchListTab = lazy(() =>
  import('../watch_list/WatchListTab').then(m => ({ default: m.WatchListTab })),
);
const EarningsPanel = lazy(() =>
  import('../earnings/EarningsPanel').then(m => ({ default: m.EarningsPanel })),
);
const NovaNewsPanel = lazy(() =>
  import('../nova_news/NovaNewsPanel').then(m => ({ default: m.NovaNewsPanel })),
);
const VolumeBoostPanel = lazy(() =>
  import('../volume_boost/VolumeBoostPanel').then(m => ({ default: m.VolumeBoostPanel })),
);
import type { Afterhours, Gapper, Mover, ScannerRow } from '../types/scanner';
import type { ScannerTableMeta } from '../hooks/useScannerPriceStream';
import type { Catalyst } from '../types/catalyst';
import type { HealthStatus } from '../types/health';
import type { MarketMode } from '../types/market';
import type { WatchlistEntry } from '../strategy/types';
import type { WatchListBoards } from '../watch_list';

export type TabModuleHostProps = {
  activeTab: ActiveTab;
  mode: MarketMode;
  health: HealthStatus;
  discoveryProvider: string;
  gappers: Gapper[];
  gainers: Mover[];
  losers: Mover[];
  afterhours: Afterhours[];
  largeCap: ScannerRow[];
  catalysts: Catalyst[];
  watchlistEntries: WatchlistEntry[];
  watchlistLoading: boolean;
  watchlistError: string | null;
  selectedSymbol: string | null;
  onSelect: (sym: string) => void;
  onOpenTrading: (sym: string) => void;
  pricesStale: boolean;
  flashSymbols: Record<string, 'up' | 'down'>;
  rowQuoteTs?: Record<string, number>;
  nowSec?: number;
  /** ADR 008 — per-table freeze/session metadata, keyed by table name. */
  tableMeta?: Record<string, ScannerTableMeta>;
  historyDate?: string | null;
  /** Sample dashboard is fixtures-only and must never mount a live fetch
   * (see SampleDashboardPage header comment). Earnings and Nova News
   * self-fetch, so they take this flag. */
  sampleMode?: boolean;
  /** The boards before the exchange filter: a hand-picked symbol's facts are never filtered away. */
  watchListBoards?: WatchListBoards;
};

const SCANNER_TABS = new Set([
  'gappers',
  'gainers',
  'losers',
  'afterhours',
  'large_cap',
  'catalysts',
]);

export function TabModuleHost(props: TabModuleHostProps) {
  const mod = getModule(props.activeTab);
  if (!mod) return null;

  const {
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
    watchlistLoading,
    watchlistError,
    selectedSymbol,
    onSelect,
    onOpenTrading,
    pricesStale,
    flashSymbols,
    rowQuoteTs = {},
    nowSec = 0,
    tableMeta = {},
    historyDate = null,
    sampleMode = false,
    watchListBoards,
  } = props;

  // Defensive: HOD / Running Up are dock-only; never blank the main column.
  if (activeTab === 'hod_momo' || activeTab === 'running_up') {
    return null;
  }

  if (SCANNER_TABS.has(activeTab)) {
    return (
      <ScannerTabPanels
        activeTab={
          activeTab as 'gappers' | 'gainers' | 'losers' | 'afterhours' | 'large_cap' | 'catalysts'
        }
        mode={mode}
        health={health}
        discoveryProvider={discoveryProvider}
        gappers={gappers}
        gainers={gainers}
        losers={losers}
        afterhours={afterhours}
        largeCap={largeCap}
        catalysts={catalysts}
        watchlistEntries={watchlistEntries}
        selectedSymbol={selectedSymbol}
        onSelect={onSelect}
        onOpenTrading={onOpenTrading}
        pricesStale={pricesStale}
        flashSymbols={flashSymbols}
        rowQuoteTs={rowQuoteTs}
        nowSec={nowSec}
        tableMeta={tableMeta}
        historyDate={historyDate}
      />
    );
  }

  if (activeTab === 'trading' || activeTab === 'reports') {
    return (
      <Suspense fallback={<TabLazyFallback />}>
        <TradingTab
          selectedSymbol={selectedSymbol}
          onSelectSymbol={onSelect}
          onOpenTrading={onOpenTrading}
          initialSection={activeTab === 'reports' ? 'reports' : 'overview'}
        />
      </Suspense>
    );
  }

  if (activeTab === 'watchlist') {
    return (
      <Suspense fallback={<TabLazyFallback />}>
        <WatchlistTab
          entries={watchlistEntries}
          loading={watchlistLoading}
          error={watchlistError}
          selectedSymbol={selectedSymbol}
          onSelectSymbol={onSelect}
          onOpenTrading={onOpenTrading}
        />
      </Suspense>
    );
  }

  if (activeTab === 'watch_list') {
    return (
      <Suspense fallback={<TabLazyFallback />}>
        <WatchListTab
          boards={watchListBoards ?? { gainers, gappers, losers, afterhours, largeCap }}
          selectedSymbol={selectedSymbol}
          onSelectSymbol={onSelect}
          onOpenTrading={onOpenTrading}
        />
      </Suspense>
    );
  }

  if (activeTab === 'volume_boost') {
    return (
      <Suspense fallback={<TabLazyFallback />}>
        <VolumeBoostPanel
          selectedSymbol={selectedSymbol}
          onSelect={onSelect}
          onOpenTrading={onOpenTrading}
          sampleMode={sampleMode}
        />
      </Suspense>
    );
  }

  if (activeTab === 'earnings') {
    if (sampleMode) {
      return <div className="empty-state">Earnings calendar is not available in Sample Data mode.</div>;
    }
    return (
      <Suspense fallback={<TabLazyFallback />}>
        <EarningsPanel
          selectedSymbol={selectedSymbol}
          onSelect={onSelect}
          onOpenTrading={onOpenTrading}
        />
      </Suspense>
    );
  }

  if (activeTab === 'nova_news') {
    return (
      <Suspense fallback={<TabLazyFallback />}>
        <NovaNewsPanel
          selectedSymbol={selectedSymbol}
          onSelect={onSelect}
          onOpenTrading={onOpenTrading}
          sampleMode={sampleMode}
        />
      </Suspense>
    );
  }

  return null;
}
