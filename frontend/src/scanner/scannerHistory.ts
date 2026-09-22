/** Shared scanner history fetch -- one date, every persisted table. */

import { historyLoadError } from './scannerHonesty';

export const SCANNER_HISTORY_PATHS = [
  'gappers',
  'movers',
  'afterhours',
  'large_cap',
] as const;

export type HistoryFetchResult = {
  ok: boolean;
  json: Record<string, unknown>;
};

export type HistoryResponseBundle = {
  gappers: HistoryFetchResult | null;
  movers: HistoryFetchResult | null;
  afterhours: HistoryFetchResult | null;
  largeCap: HistoryFetchResult | null;
};

export type HistoryTables = {
  gappers?: unknown[];
  gainers?: unknown[];
  losers?: unknown[];
  afterhours?: unknown[];
  largeCap: unknown[];
};

/** Scanner tables a history view shows (the keys the board reads). */
export type HistoryTableKey = 'gappers' | 'gainers' | 'losers' | 'afterhours' | 'large_cap';

function rowsFrom(json: Record<string, unknown> | undefined, key: string): unknown[] {
  const value = json?.[key];
  return Array.isArray(value) ? value : [];
}

/**
 * Rows per table for one date. A table whose request failed comes back empty
 * and is named in `failed` -- never left holding today's live rows under
 * "Viewing <date>" (QA C51). `error` is set only when every request failed.
 */
export function historyTablesFromResponses(
  date: string,
  responses: HistoryResponseBundle,
): { tables: HistoryTables; error: string | null; failed: HistoryTableKey[] } {
  const gOk = responses.gappers?.ok === true;
  const mOk = responses.movers?.ok === true;
  const aOk = responses.afterhours?.ok === true;
  const lOk = responses.largeCap?.ok === true;
  const largeCap = rowsFrom(responses.largeCap?.json, 'large_cap');
  const failed: HistoryTableKey[] = [];
  if (!gOk) failed.push('gappers');
  if (!mOk) failed.push('gainers', 'losers');
  if (!aOk) failed.push('afterhours');
  if (!lOk) failed.push('large_cap');

  if (!gOk && !mOk && !aOk && !lOk) {
    return {
      tables: { gappers: [], gainers: [], losers: [], afterhours: [], largeCap: [] },
      error: historyLoadError(date),
      failed,
    };
  }

  const tables: HistoryTables = {
    largeCap,
    gappers: gOk ? rowsFrom(responses.gappers!.json, 'gappers') : [],
    gainers: mOk ? rowsFrom(responses.movers!.json, 'gainers') : [],
    losers: mOk ? rowsFrom(responses.movers!.json, 'losers') : [],
    afterhours: aOk ? rowsFrom(responses.afterhours!.json, 'afterhours') : [],
  };
  return { tables, error: null, failed };
}

async function fetchHistoryJson(
  fetchImpl: typeof fetch,
  url: string,
): Promise<HistoryFetchResult | null> {
  try {
    const res = await fetchImpl(url);
    if (!res.ok) return { ok: false, json: {} };
    const data = await res.json();
    if (!data || typeof data !== 'object' || Array.isArray(data)) {
      return { ok: true, json: {} };
    }
    return { ok: true, json: data as Record<string, unknown> };
  } catch {
    return null;
  }
}

export async function fetchScannerHistory(
  apiUrl: string,
  date: string,
  fetchImpl: typeof fetch = fetch,
): Promise<{ tables: HistoryTables; error: string | null; failed: HistoryTableKey[] }> {
  const [gappers, movers, afterhours, largeCap] = await Promise.all(
    SCANNER_HISTORY_PATHS.map((path) =>
      fetchHistoryJson(fetchImpl, `${apiUrl}/history/${path}/${date}`),
    ),
  );
  return historyTablesFromResponses(date, {
    gappers,
    movers,
    afterhours,
    largeCap,
  });
}
