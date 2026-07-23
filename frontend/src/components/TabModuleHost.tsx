/**
 * Renders the active tab body via registry id lookup (Phase 4).
 * Keeps DashboardPage under the component size limit.
 */
import { HodMomoSection } from '../hod_momo/HodMomoSection';
import type { useHodMomoConfig } from '../hod_momo/useHodMomoConfig';
import type { useHodMomoStream } from '../hod_momo/useHodMomoStream';
import { ScannerTabPanels } from './ScannerTabPanels';
import { DashboardTab } from '../pages/DashboardTab';
import { TradingTab } from '../ibkr/TradingTab';
import { WatchlistTab } from '../strategy/WatchlistTab';
import { getModule, type ActiveTab } from '../workspace/registry';
import type { Afterhours, Gapper, Mover } from '../types/scanner';
import type { ScannerTableMeta } from '../hooks/useScannerPriceStream';
import type { Catalyst } from '../types/catalyst';
import type { HealthStatus } from '../types/health';
import type { MarketMode } from './AppHeader';
import type { WatchlistEntry } from '../strategy/types';
import type { useExchangeFilter } from '../hooks/useExchangeFilter';
import type { useSettingsForm } from '../hooks/useSettingsForm';

type HodStream = ReturnType<typeof useHodMomoStream>;
type HodConfig = ReturnType<typeof useHodMomoConfig>;
type Settings = ReturnType<typeof useSettingsForm>;
type ExchangeFilter = ReturnType<typeof useExchangeFilter>;

export type TabModuleHostProps = {
  activeTab: ActiveTab;
  settings: Settings;
  filter: ExchangeFilter;
  mode: MarketMode;
  health: HealthStatus;
  discoveryProvider: string;
  gappers: Gapper[];
  gainers: Mover[];
  losers: Mover[];
  afterhours: Afterhours[];
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
  hodMomoStream: HodStream;
  hodMomoConfig: HodConfig;
  showHodSettings: boolean;
  onToggleHodSettings: () => void;
  onCloseHodSettings: () => void;
};

const SCANNER_TABS = new Set([
  'gappers',
  'gainers',
  'losers',
  'afterhours',
  'catalysts',
]);

export function TabModuleHost(props: TabModuleHostProps) {
  const mod = getModule(props.activeTab);
  if (!mod) return null;

  const {
    activeTab,
    settings,
    filter,
    mode,
    health,
    discoveryProvider,
    gappers,
    gainers,
    losers,
    afterhours,
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
    hodMomoStream,
    hodMomoConfig,
    showHodSettings,
    onToggleHodSettings,
    onCloseHodSettings,
  } = props;

  if (activeTab === 'dashboard') {
    return (
      <DashboardTab
        filter={filter}
        apiKey={settings.apiKey}
        onApiKeyChange={settings.setApiKey}
        apiSecret={settings.apiSecret}
        onApiSecretChange={settings.setApiSecret}
        baseUrl={settings.baseUrl}
        onBaseUrlChange={settings.setBaseUrl}
        dataFeed={settings.dataFeed}
        onDataFeedChange={settings.setDataFeed}
        dataFeedOptions={settings.dataFeedOptions}
        discoveryProvider={settings.discoveryProvider}
        onSubmit={settings.handleConfigUpdate}
      />
    );
  }

  if (SCANNER_TABS.has(activeTab)) {
    return (
      <ScannerTabPanels
        activeTab={activeTab as 'gappers' | 'gainers' | 'losers' | 'afterhours' | 'catalysts'}
        mode={mode}
        health={health}
        discoveryProvider={discoveryProvider}
        gappers={gappers}
        gainers={gainers}
        losers={losers}
        afterhours={afterhours}
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
      />
    );
  }

  if (activeTab === 'hod_momo' || activeTab === 'running_up') {
    // Extracted + memoized so the 1Hz `nowSec` clock this component receives
    // (for the scanner tabs above) cannot force this subtree to re-render.
    return (
      <HodMomoSection
        activeTab={activeTab}
        hodMomoStream={hodMomoStream}
        hodMomoConfig={hodMomoConfig}
        selectedSymbol={selectedSymbol}
        onSelect={onSelect}
        onOpenTrading={onOpenTrading}
        showHodSettings={showHodSettings}
        onToggleHodSettings={onToggleHodSettings}
        onCloseHodSettings={onCloseHodSettings}
      />
    );
  }

  if (activeTab === 'trading' || activeTab === 'reports') {
    return (
      <TradingTab
        selectedSymbol={selectedSymbol}
        onSelectSymbol={onSelect}
        onOpenTrading={onOpenTrading}
        initialSection={activeTab === 'reports' ? 'reports' : 'overview'}
      />
    );
  }

  if (activeTab === 'watchlist') {
    return (
      <WatchlistTab
        entries={watchlistEntries}
        loading={watchlistLoading}
        error={watchlistError}
        selectedSymbol={selectedSymbol}
        onSelectSymbol={onSelect}
        onOpenTrading={onOpenTrading}
      />
    );
  }

  return null;
}
