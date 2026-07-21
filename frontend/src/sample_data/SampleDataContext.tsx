/**
 * Sample-data isolation boundary. Only SampleShell mounts this provider.
 * Live DashboardPage must never be a child — hooks return fixtures and skip network.
 */
import { createContext, useContext, type ReactNode } from 'react';
import type { AlertObject, HodMomoConfigState } from '../hod_momo/types';
import type { HealthStatus } from '../types/health';
import type { Afterhours, Gapper, Mover } from '../types/scanner';
import type { Catalyst } from '../types/catalyst';
import type { NovaOsDecision, SetupSignal, WatchlistEntry } from '../strategy/types';
import { SAMPLE_HOD_ALERTS, SAMPLE_HOD_CONFIG } from './sampleHod';
import {
  SAMPLE_AFTERHOURS,
  SAMPLE_CATALYSTS,
  SAMPLE_GAPPERS,
  SAMPLE_GAINERS,
  SAMPLE_LOSERS,
} from './sampleRows';
import {
  SAMPLE_DECISIONS,
  SAMPLE_SIGNALS,
  SAMPLE_WATCHLIST,
  sampleDecisionForSymbol,
} from './sampleStrategy';
import { sampleTickerDetail } from './sampleTicker';
import type { TickerDetail } from '../types/ticker';

export type SampleDataBundle = {
  gappers: Gapper[];
  gainers: Mover[];
  losers: Mover[];
  afterhours: Afterhours[];
  catalysts: Catalyst[];
  hodAlerts: AlertObject[];
  hodConfig: HodMomoConfigState;
  watchlist: WatchlistEntry[];
  decisions: NovaOsDecision[];
  signals: SetupSignal[];
  health: HealthStatus;
  decisionForSymbol: (symbol: string) => NovaOsDecision | null;
  tickerDetail: (symbol: string) => TickerDetail;
};

const SAMPLE_BUNDLE: SampleDataBundle = {
  gappers: SAMPLE_GAPPERS,
  gainers: SAMPLE_GAINERS,
  losers: SAMPLE_LOSERS,
  afterhours: SAMPLE_AFTERHOURS,
  catalysts: SAMPLE_CATALYSTS,
  hodAlerts: SAMPLE_HOD_ALERTS,
  hodConfig: SAMPLE_HOD_CONFIG,
  watchlist: SAMPLE_WATCHLIST,
  decisions: SAMPLE_DECISIONS,
  signals: SAMPLE_SIGNALS,
  health: { status: 'ok', latency_ms: 12 },
  decisionForSymbol: sampleDecisionForSymbol,
  tickerDetail: sampleTickerDetail,
};

const SampleDataContext = createContext<SampleDataBundle | null>(null);

export function SampleDataProvider({ children }: { children: ReactNode }) {
  return (
    <SampleDataContext.Provider value={SAMPLE_BUNDLE}>{children}</SampleDataContext.Provider>
  );
}

/** Null outside the sample shell — live hooks must treat null as “use network”. */
export function useSampleDataOptional(): SampleDataBundle | null {
  return useContext(SampleDataContext);
}

export function useSampleData(): SampleDataBundle {
  const ctx = useContext(SampleDataContext);
  if (!ctx) {
    throw new Error('useSampleData must be used within SampleDataProvider');
  }
  return ctx;
}
