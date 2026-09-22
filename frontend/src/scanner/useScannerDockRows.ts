/**
 * Rows + counts for scanner-dock roster pills (live feed or sample fixtures).
 */
import { useMemo } from 'react';
import { DISCOVERY_PROVIDER_DEFAULT } from '../constants';
import type { ScannerTableMeta } from '../hooks/useScannerPriceStream';
import type { ScannerDockRosterMode } from '../hod_momo/scannerDockModes';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import { useSettingsOptional } from '../settings/SettingsContext';
import type { WatchlistEntry } from '../strategy/types';
import type { Catalyst } from '../types/catalyst';
import type { HealthStatus } from '../types/health';
import type { MarketMode } from '../types/market';
import type { Afterhours, Gapper, Mover } from '../types/scanner';
import type { ActiveTab } from '../workspace/registry';
import { useLiveScannerFeedOptional } from './ScannerDataContext';

export type ScannerDockRows = {
  gappers: Gapper[];
  gainers: Mover[];
  losers: Mover[];
  afterhours: Afterhours[];
  catalysts: Catalyst[];
  watchlistEntries: WatchlistEntry[];
  mode: MarketMode;
  health: HealthStatus;
  discoveryProvider: string;
  pricesStale: boolean;
  flashSymbols: Record<string, 'up' | 'down'>;
  rowQuoteTs: Record<string, number>;
  nowSec: number;
  tableMeta: Record<string, ScannerTableMeta>;
  counts: Record<ScannerDockRosterMode, number>;
  /** Declares the dock's own table for L1 streaming (separate from main tab). */
  setL1DockTab: ((tab: ActiveTab | null) => void) | null;
};

export function useScannerDockRows(): ScannerDockRows | null {
  const live = useLiveScannerFeedOptional();
  const sample = useSampleDataOptional();
  const settings = useSettingsOptional();
  const filter = settings?.exchangeFilter;

  return useMemo(() => {
    if (live) {
      const gappers = filter ? filter.filterRows(live.gappers) : live.gappers;
      const gainers = filter ? filter.filterRows(live.gainers) : live.gainers;
      const losers = filter ? filter.filterRows(live.losers) : live.losers;
      const afterhours = filter ? filter.filterRows(live.afterhours) : live.afterhours;
      return {
        gappers,
        gainers,
        losers,
        afterhours,
        catalysts: live.catalysts,
        watchlistEntries: [],
        mode: live.mode,
        health: live.health,
        discoveryProvider: settings?.settings.discoveryProvider ?? 'ibkr',
        pricesStale: live.pricesStale,
        flashSymbols: live.flashSymbols,
        rowQuoteTs: live.rowQuoteTs,
        nowSec: live.now,
        tableMeta: live.tableMeta,
        counts: {
          gappers: gappers.length,
          gainers: gainers.length,
          losers: losers.length,
          afterhours: afterhours.length,
          catalysts: live.catalysts.length,
        },
        setL1DockTab: live.setL1DockTab,
      };
    }
    if (sample) {
      return {
        gappers: sample.gappers,
        gainers: sample.gainers,
        losers: sample.losers,
        afterhours: sample.afterhours,
        catalysts: sample.catalysts,
        watchlistEntries: sample.watchlist,
        mode: 'market',
        health: sample.health,
        discoveryProvider: DISCOVERY_PROVIDER_DEFAULT,
        pricesStale: false,
        flashSymbols: {},
        rowQuoteTs: {},
        nowSec: Date.now() / 1000,
        tableMeta: {},
        counts: {
          gappers: sample.gappers.length,
          gainers: sample.gainers.length,
          losers: sample.losers.length,
          afterhours: sample.afterhours.length,
          catalysts: sample.catalysts.length,
        },
        setL1DockTab: null,
      };
    }
    return null;
  }, [live, sample, filter, settings?.settings.discoveryProvider]);
}
