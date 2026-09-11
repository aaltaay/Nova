import { describe, expect, it } from 'vitest';
import {
  SCANNER_CATALYSTS_EMPTY,
  SCANNER_CATALYSTS_FEED_DOWN,
  SCANNER_HONESTY_LAST_GOOD,
  SCANNER_HONESTY_UNAVAILABLE,
  SCANNER_PRICE_NO_L1,
  applyLastGoodRows,
  catalystsEmptyCopy,
  feedErrorFromPayload,
  mergeRestTableMeta,
  priceAgeChipText,
  scannerHonestyChip,
  showPriceAgeChip,
  tableHonestyLabel,
} from './scannerHonesty';

describe('applyLastGoodRows', () => {
  it('keeps previous rows and flags lastGood when empty payload arrives', () => {
    const prev = [{ symbol: 'AAPL' }];
    expect(applyLastGoodRows(prev, [])).toEqual({ rows: prev, lastGood: true });
  });

  it('replaces when the payload has names', () => {
    const prev = [{ symbol: 'AAPL' }];
    const incoming = [{ symbol: 'MSFT' }];
    expect(applyLastGoodRows(prev, incoming)).toEqual({ rows: incoming, lastGood: false });
  });

  it('ignores a non-array payload', () => {
    expect(applyLastGoodRows([{ symbol: 'AAPL' }], null)).toBeNull();
  });
});

describe('scannerHonestyChip', () => {
  it('prefers subscriptionError, then feed_error, then unavailable, then last-good', () => {
    expect(
      scannerHonestyChip({
        subscriptionError: 'L1 capacity',
        feedError: 'gappers: TimeoutError',
        tableState: 'unavailable',
        lastGood: true,
      }),
    ).toBe('L1 capacity');
    expect(
      scannerHonestyChip({
        feedError: 'gappers: TimeoutError',
        tableState: 'unavailable',
        lastGood: true,
      }),
    ).toBe('gappers: TimeoutError');
    expect(scannerHonestyChip({ tableState: 'unavailable', lastGood: true })).toBe(
      SCANNER_HONESTY_UNAVAILABLE,
    );
    expect(scannerHonestyChip({ lastGood: true })).toBe(SCANNER_HONESTY_LAST_GOOD);
    expect(scannerHonestyChip({ tableState: 'live' })).toBeNull();
  });
});

describe('priceAgeChipText', () => {
  const formatAge = (n: number) => `${n}s ago`;

  it('says no L1 yet when lastPriceTs is 0 (does not use roster lastScan)', () => {
    expect(
      priceAgeChipText({ lastPriceTs: 0, secondsAgo: 12, pricesStale: false, formatAge }),
    ).toBe(SCANNER_PRICE_NO_L1);
  });

  it('uses age / stale only after an L1 tick', () => {
    expect(
      priceAgeChipText({ lastPriceTs: 100, secondsAgo: 3, pricesStale: false, formatAge }),
    ).toBe('3s ago');
    expect(
      priceAgeChipText({ lastPriceTs: 100, secondsAgo: 9, pricesStale: true, formatAge }),
    ).toBe('stale · 9s ago');
  });
});

describe('showPriceAgeChip', () => {
  it('shows on a live scanner tab even when lastPriceTs is 0', () => {
    expect(showPriceAgeChip({ historyDate: null, lastPriceTs: 0, secondsAgo: null })).toBe(true);
    expect(showPriceAgeChip({ historyDate: '2026-08-24', lastPriceTs: 0, secondsAgo: 1 })).toBe(
      false,
    );
  });
});

describe('tableHonestyLabel', () => {
  it('paints unavailable before last-good or frozen', () => {
    const label = tableHonestyLabel(
      {
        state: 'unavailable',
        session_key: 's',
        revision: 1,
        roster_ts: 0,
        quote_ts: 0,
        frozen_at: 0,
        source: 'ws',
      },
      true,
    );
    expect(label?.kind).toBe('honesty');
    expect(label?.text).toMatch(/Unavailable/);
  });
});

describe('catalystsEmptyCopy', () => {
  it('does not claim scan running for an honest empty or a dead feed', () => {
    expect(catalystsEmptyCopy({ healthStatus: 'ok' })).toBe(SCANNER_CATALYSTS_EMPTY);
    expect(catalystsEmptyCopy({ healthStatus: 'disconnected' })).toBe(SCANNER_CATALYSTS_FEED_DOWN);
    expect(
      catalystsEmptyCopy({ healthStatus: 'ok', fetchError: 'Catalysts feed failed (HTTP 503).' }),
    ).toBe('Catalysts feed failed (HTTP 503).');
    expect(catalystsEmptyCopy({ healthStatus: 'ok' })).not.toMatch(/scan running/i);
  });
});

describe('rest honesty helpers', () => {
  it('reads feed_error and merges table_state', () => {
    expect(feedErrorFromPayload({ feed_error: 'movers: IbkrDiscoveryError' })).toBe(
      'movers: IbkrDiscoveryError',
    );
    expect(feedErrorFromPayload({ feed_error: null })).toBeNull();
    expect(feedErrorFromPayload({})).toBeUndefined();
    const next = mergeRestTableMeta({}, 'gappers', 'unavailable', 12);
    expect(next.gappers.state).toBe('unavailable');
    expect(next.gappers.roster_ts).toBe(12);
  });
});
