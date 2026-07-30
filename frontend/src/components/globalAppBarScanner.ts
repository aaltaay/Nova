import type { ChangeEvent } from 'react';
import type { HealthStatus } from '../types/health';
import type { IbkrMode } from '../ibkr/types';

/** Shared status block (market mode, chips, history, lookup) for GlobalAppBar on Scanner + Trader. */
export type GlobalAppBarScanner = {
  mode: 'premarket' | 'market' | 'afterhours' | 'closed' | 'loading';
  health: HealthStatus;
  activeFeed: string;
  feedFellBack: boolean;
  secondsAgo: number | null;
  pricesStale?: boolean;
  ibkrConnected?: boolean;
  ibkrMode?: IbkrMode;
  ibkrGatewayMode?: 'paper' | 'live' | null;
  historyDate: string | null;
  historyDates: string[];
  onHistoryChange: (e: ChangeEvent<HTMLSelectElement>) => void;
  onLookup: (symbol: string) => void;
  showScannerSource?: boolean;
  discoveryProvider?: string;
  onBackendStarted?: () => void;
  sampleDataActive?: boolean;
  onSampleDataToggle?: (active: boolean) => void;
};

export const SCANNER_MODE_LABELS: Record<GlobalAppBarScanner['mode'], string> = {
  loading: 'Connecting…',
  premarket: 'Pre-Market',
  market: 'Market Hours',
  afterhours: 'After Hours',
  closed: 'Market Closed',
};

export function fmtHistoryDateShort(dateStr: string): string {
  const [y, m, d] = dateStr.split('-').map(Number);
  const dt = new Date(y, m - 1, d);
  return dt.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
}
