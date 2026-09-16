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

function rowsFrom(json: Record<string, unknown> | undefined, key: string): unknown[] {
  const value = json?.[key];
  return Array.isArray(value) ? value : [];
}

export function historyTablesFromResponses(
  date: string,
  responses: HistoryResponseBundle,
): { tables: HistoryTables; error: string | null } {
  const gOk = responses.gappers?.ok === true;
  const mOk = responses.movers?.ok === true;
  const aOk = responses.afterhours?.ok === true;
  const lOk = responses.largeCap?.ok === true;
  const largeCap = rowsFrom(responses.largeCap?.json, 'large_cap');

  if (!gOk && !mOk && !aOk && !lOk) {
    return { tables: { largeCap: [] }, error: historyLoadError(date) };
  }

  const tables: HistoryTables = { largeCap };
  if (gOk) tables.gappers = rowsFrom(responses.gappers!.json, 'gappers');
  if (mOk) {
    tables.gainers = rowsFrom(responses.movers!.json, 'gainers');
    tables.losers = rowsFrom(responses.movers!.json, 'losers');
  }
  if (aOk) tables.afterhours = rowsFrom(responses.afterhours!.json, 'afterhours');
  return { tables, error: null };
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
): Promise<{ tables: HistoryTables; error: string | null }> {
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
