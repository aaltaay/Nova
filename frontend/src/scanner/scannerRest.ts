/**
 * Scanner REST envelopes: read one response honestly and say what failed.
 *
 * QA C31: a failed /api/movers (500 text, HTML, `null`, a list, malformed
 * JSON) used to be swallowed -- the failure counter was reset as soon as the
 * headers arrived, so the grace count was never reached, and the board then
 * read "Market is closed -- showing last available data" over an empty table.
 * Here every route answers either a readable object or a named failure.
 *
 * QA C48: persistent-authoritative desks (ADR 008) fetch the rows once and
 * then follow /ws/scanner; the mode / health / feed_error envelope now comes
 * from GET /api/scan/envelope on a slow poll instead of freezing at mount.
 *
 * Pure: no module state.
 */
import type { ScannerScanAges } from '../utils/scanAge';

export type EnvelopeRead =
  | { ok: true; data: Record<string, unknown> }
  | { ok: false; error: string };

/** The table keys an envelope reports, and which scan-age slot each feeds. */
export const SCANNER_ENVELOPE_TABLE_AGE: Record<string, keyof ScannerScanAges> = {
  gappers: 'gappers',
  gainers: 'movers',
  losers: 'movers',
  afterhours: 'afterhours',
  large_cap: 'largeCap',
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return value != null && typeof value === 'object' && !Array.isArray(value);
}

/** One scanner route's reply: a JSON object, or the reason it is not one. */
export async function readScannerEnvelope(res: Response, route: string): Promise<EnvelopeRead> {
  if (!res.ok) return { ok: false, error: `${route} answered HTTP ${res.status}` };
  let data: unknown;
  try {
    data = await res.json();
  } catch {
    return { ok: false, error: `${route} answered a body that is not JSON` };
  }
  if (!isRecord(data)) return { ok: false, error: `${route} answered an unreadable body` };
  return { ok: true, data };
}

/** One line for the board: null when every route answered. */
export function scannerRestErrorText(failures: readonly string[]): string | null {
  if (failures.length === 0) return null;
  return `Scanner feed failed: ${failures.join('; ')}`;
}

/** Transport failure (timeout, refused connection) as a board line. */
export function scannerRestTransportError(err: unknown): string {
  const name = err instanceof Error ? err.name : '';
  if (name === 'TimeoutError' || name === 'AbortError') {
    return 'Scanner feed failed: the scanner routes did not answer in time';
  }
  return 'Scanner feed failed: the scanner routes could not be reached';
}

/** Next retry delay: doubles from `base` up to `max`. */
export function nextRetryDelay(attempt: number, base: number, max: number): number {
  const n = Math.max(0, Math.floor(attempt));
  return Math.min(max, base * 2 ** n);
}

/** Per-table `{table_state, roster_ts, last_scan}` rows of an envelope, each checked. */
export function envelopeTables(
  data: Record<string, unknown>,
): Array<{ table: string; state: unknown; rosterTs: unknown; lastScan: number | null }> {
  const tables = data.tables;
  if (!isRecord(tables)) return [];
  const out: Array<{ table: string; state: unknown; rosterTs: unknown; lastScan: number | null }> = [];
  for (const table of Object.keys(SCANNER_ENVELOPE_TABLE_AGE)) {
    const row = tables[table];
    if (!isRecord(row)) continue;
    const lastScan = typeof row.last_scan === 'number' && Number.isFinite(row.last_scan) ? row.last_scan : null;
    out.push({ table, state: row.table_state, rosterTs: row.roster_ts, lastScan });
  }
  return out;
}
