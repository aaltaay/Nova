import { describe, expect, it, vi } from 'vitest';
import { historyLoadError } from './scannerHonesty';
import {
  SCANNER_HISTORY_PATHS,
  fetchScannerHistory,
  historyTablesFromResponses,
} from './scannerHistory';

const DATE = '2026-09-15';

function jsonOk(body: unknown): Response {
  return {
    ok: true,
    json: async () => body,
  } as Response;
}

function jsonFail(): Response {
  return {
    ok: false,
    json: async () => ({}),
  } as Response;
}

describe('SCANNER_HISTORY_PATHS', () => {
  it('includes large_cap with the day-trade snapshots', () => {
    expect(SCANNER_HISTORY_PATHS).toEqual([
      'gappers',
      'movers',
      'afterhours',
      'large_cap',
    ]);
  });
});

describe('historyTablesFromResponses', () => {
  it('applies large_cap rows when the snapshot is present', () => {
    const { tables, error } = historyTablesFromResponses(DATE, {
      gappers: { ok: true, json: { gappers: [{ symbol: 'CRE' }] } },
      movers: { ok: true, json: { gainers: [{ symbol: 'AAA' }], losers: [] } },
      afterhours: { ok: true, json: { afterhours: [] } },
      largeCap: { ok: true, json: { large_cap: [{ symbol: 'NVDA' }] } },
    });
    expect(error).toBeNull();
    expect(tables.gappers).toEqual([{ symbol: 'CRE' }]);
    expect(tables.largeCap).toEqual([{ symbol: 'NVDA' }]);
  });

  it('clears largeCap when that date has no snapshot, without failing others', () => {
    const { tables, error } = historyTablesFromResponses(DATE, {
      gappers: { ok: true, json: { gappers: [{ symbol: 'CRE' }] } },
      movers: { ok: true, json: { gainers: [], losers: [] } },
      afterhours: { ok: true, json: { afterhours: [] } },
      largeCap: { ok: true, json: {} },
    });
    expect(error).toBeNull();
    expect(tables.gappers).toEqual([{ symbol: 'CRE' }]);
    expect(tables.largeCap).toEqual([]);
  });

  it('clears largeCap on a hard miss without setting a global history error', () => {
    const { tables, error } = historyTablesFromResponses(DATE, {
      gappers: { ok: true, json: { gappers: [{ symbol: 'CRE' }] } },
      movers: { ok: true, json: { gainers: [], losers: [] } },
      afterhours: { ok: true, json: { afterhours: [] } },
      largeCap: { ok: false, json: {} },
    });
    expect(error).toBeNull();
    expect(tables.gappers).toEqual([{ symbol: 'CRE' }]);
    expect(tables.largeCap).toEqual([]);
  });

  it('sets a load error only when every snapshot request fails', () => {
    const { tables, error } = historyTablesFromResponses(DATE, {
      gappers: null,
      movers: null,
      afterhours: null,
      largeCap: null,
    });
    expect(error).toBe(historyLoadError(DATE));
    expect(tables.largeCap).toEqual([]);
    expect(tables.gappers).toBeUndefined();
  });
});

describe('fetchScannerHistory', () => {
  it('GETs large_cap on the same date as gappers/movers/AH', async () => {
    const fetchImpl = vi.fn(async (url: string) => {
      if (url.endsWith(`/history/gappers/${DATE}`)) {
        return jsonOk({ gappers: [{ symbol: 'CRE' }] });
      }
      if (url.endsWith(`/history/movers/${DATE}`)) {
        return jsonOk({ gainers: [{ symbol: 'AAA' }], losers: [] });
      }
      if (url.endsWith(`/history/afterhours/${DATE}`)) {
        return jsonOk({ afterhours: [] });
      }
      if (url.endsWith(`/history/large_cap/${DATE}`)) {
        return jsonOk({ large_cap: [{ symbol: 'NVDA' }] });
      }
      return jsonFail();
    });

    const { tables, error } = await fetchScannerHistory('/api', DATE, fetchImpl);
    expect(error).toBeNull();
    expect(tables.largeCap).toEqual([{ symbol: 'NVDA' }]);
    expect(tables.gappers).toEqual([{ symbol: 'CRE' }]);
    expect(fetchImpl.mock.calls.map(([url]) => url)).toEqual([
      `/api/history/gappers/${DATE}`,
      `/api/history/movers/${DATE}`,
      `/api/history/afterhours/${DATE}`,
      `/api/history/large_cap/${DATE}`,
    ]);
  });

  it('keeps gappers when large_cap fetch throws', async () => {
    const fetchImpl = vi.fn(async (url: string) => {
      if (url.includes('/history/large_cap/')) {
        throw new Error('network down');
      }
      if (url.includes('/history/gappers/')) {
        return jsonOk({ gappers: [{ symbol: 'CRE' }] });
      }
      return jsonOk({});
    });

    const { tables, error } = await fetchScannerHistory('/api', DATE, fetchImpl);
    expect(error).toBeNull();
    expect(tables.gappers).toEqual([{ symbol: 'CRE' }]);
    expect(tables.largeCap).toEqual([]);
  });
});
