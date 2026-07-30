/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, beforeEach } from 'vitest';
import type { GlobalAppBarScanner } from './globalAppBarScanner';
import {
  getScannerBarSnapshot,
  patchScannerBarProps,
  publishGlobalBarCore,
  resetScannerBarStoreForTests,
  setGlobalBarHistoryDate,
} from './scannerBarStore';

function core(
  overrides: Partial<
    Omit<GlobalAppBarScanner, 'secondsAgo' | 'pricesStale' | 'historyDate' | 'historyDates'>
  > = {},
): Omit<GlobalAppBarScanner, 'secondsAgo' | 'pricesStale' | 'historyDate' | 'historyDates'> {
  return {
    mode: 'market',
    health: { status: 'connected', latency_ms: 10 },
    activeFeed: 'ibkr',
    feedFellBack: false,
    ibkrConnected: true,
    ibkrMode: 'live',
    ibkrGatewayMode: 'live',
    onHistoryChange: () => {},
    onLookup: () => {},
    showScannerSource: true,
    discoveryProvider: 'ibkr',
    ...overrides,
  };
}

describe('scannerBarStore', () => {
  beforeEach(() => {
    resetScannerBarStoreForTests();
  });

  it('keeps status strip after freshness patch (Trader must not clear)', () => {
    publishGlobalBarCore(core());
    patchScannerBarProps({ secondsAgo: 3, pricesStale: false });
    publishGlobalBarCore(core({ mode: 'afterhours' }));
    const snap = getScannerBarSnapshot();
    expect(snap).not.toBeNull();
    expect(snap!.mode).toBe('afterhours');
    expect(snap!.secondsAgo).toBe(3);
  });

  it('preserves history selection across core republish', () => {
    publishGlobalBarCore(core());
    setGlobalBarHistoryDate('2026-07-15');
    publishGlobalBarCore(core());
    expect(getScannerBarSnapshot()!.historyDate).toBe('2026-07-15');
  });
});
