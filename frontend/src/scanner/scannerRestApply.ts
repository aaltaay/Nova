/**
 * Apply scanner REST replies to the scanner state (split from
 * hooks/useScannerData.ts to keep it under the file-size limit).
 *
 * Each table route is read through `readScannerEnvelope`: a readable object
 * is applied (rows through the shape gate, envelope, table meta, scan age), a
 * failure is returned by name so the board can say which route failed (QA C31).
 */
import type { Dispatch, SetStateAction } from 'react';
import type { ScannerTableMeta } from '../hooks/useScannerPriceStream';
import type { Catalyst } from '../types/catalyst';
import type { ScannerRow } from '../types/scanner';
import type { ScannerScanAges } from '../utils/scanAge';
import {
  applyRosterTable,
  catalystsHttpError,
  mergeRestTableMeta,
  SCANNER_CATALYSTS_UNREADABLE,
} from './scannerHonesty';
import { envelopeTables, readScannerEnvelope, SCANNER_ENVELOPE_TABLE_AGE } from './scannerRest';
import { normalizeCatalystRows } from './scannerRowShape';

type RowSetter = Dispatch<SetStateAction<ScannerRow[]>>;

export type ScannerRestSink = {
  applyEnvelope: (data: Record<string, unknown>) => void;
  setGappers: RowSetter;
  setGainers: RowSetter;
  setLosers: RowSetter;
  setAfterhours: RowSetter;
  setLargeCap: RowSetter;
  setLastGood: Dispatch<SetStateAction<Record<string, boolean>>>;
  setTableMeta: Dispatch<SetStateAction<Record<string, ScannerTableMeta>>>;
  setScanAges: Dispatch<SetStateAction<ScannerScanAges>>;
};

export type ScannerTableReplies = {
  gappers: Response;
  movers: Response;
  afterhours: Response;
  largeCap: Response;
};

function lastScan(data: Record<string, unknown>): number | null {
  return typeof data.last_scan === 'number' && Number.isFinite(data.last_scan) && data.last_scan > 0
    ? data.last_scan
    : null;
}

/** Apply the four table replies; returns one line per failed route (empty when all answered). */
export async function applyScannerTableReplies(
  replies: ScannerTableReplies,
  sink: ScannerRestSink,
): Promise<string[]> {
  const failures: string[] = [];
  const nextAges: Partial<ScannerScanAges> = {};

  const gap = await readScannerEnvelope(replies.gappers, '/api/gappers');
  if (gap.ok) {
    sink.applyEnvelope(gap.data);
    applyRosterTable(sink.setGappers, sink.setLastGood, 'gappers', gap.data.gappers);
    sink.setTableMeta(prev => mergeRestTableMeta(prev, 'gappers', gap.data.table_state, gap.data.roster_ts));
    const ts = lastScan(gap.data);
    if (ts) nextAges.gappers = ts;
  } else failures.push(gap.error);

  const movers = await readScannerEnvelope(replies.movers, '/api/movers');
  if (movers.ok) {
    const data = movers.data;
    sink.applyEnvelope(data);
    applyRosterTable(sink.setGainers, sink.setLastGood, 'gainers', data.gainers);
    applyRosterTable(sink.setLosers, sink.setLastGood, 'losers', data.losers);
    sink.setTableMeta(prev => {
      const next = mergeRestTableMeta(prev, 'gainers', data.table_state, data.roster_ts);
      return mergeRestTableMeta(next, 'losers', data.loser_table_state, data.loser_roster_ts);
    });
    const ts = lastScan(data);
    if (ts) nextAges.movers = ts;
  } else failures.push(movers.error);

  const ah = await readScannerEnvelope(replies.afterhours, '/api/afterhours');
  if (ah.ok) {
    sink.applyEnvelope(ah.data);
    applyRosterTable(sink.setAfterhours, sink.setLastGood, 'afterhours', ah.data.afterhours);
    sink.setTableMeta(prev => mergeRestTableMeta(prev, 'afterhours', ah.data.table_state, ah.data.roster_ts));
    const ts = lastScan(ah.data);
    if (ts) nextAges.afterhours = ts;
  } else failures.push(ah.error);

  const lc = await readScannerEnvelope(replies.largeCap, '/api/large-cap');
  if (lc.ok) {
    sink.applyEnvelope(lc.data);
    applyRosterTable(sink.setLargeCap, sink.setLastGood, 'large_cap', lc.data.large_cap);
    sink.setTableMeta(prev => mergeRestTableMeta(prev, 'large_cap', lc.data.table_state, lc.data.roster_ts));
    const ts = lastScan(lc.data);
    if (ts) nextAges.largeCap = ts;
  } else failures.push(lc.error);

  if (Object.keys(nextAges).length > 0) sink.setScanAges(prev => ({ ...prev, ...nextAges }));
  return failures;
}

/** The catalysts reply: its rows, or the error line for the Catalysts panel. */
export async function readCatalystReply(
  res: Response,
): Promise<{ rows: Catalyst[]; error: null } | { rows: null; error: string }> {
  if (!res.ok) return { rows: null, error: catalystsHttpError(res.status) };
  const read = await readScannerEnvelope(res, '/api/news-catalysts');
  const rows = read.ok ? normalizeCatalystRows(read.data.catalysts) : null;
  return rows ? { rows, error: null } : { rows: null, error: SCANNER_CATALYSTS_UNREADABLE };
}

/** Apply an envelope-only poll (QA C48): table state + scan ages, never rows. */
export function applyEnvelopeTables(data: Record<string, unknown>, sink: ScannerRestSink): void {
  const rows = envelopeTables(data);
  if (rows.length === 0) return;
  sink.setTableMeta(prev => rows.reduce((meta, t) => mergeRestTableMeta(meta, t.table, t.state, t.rosterTs), prev));
  sink.setScanAges(prev => {
    let next = prev;
    for (const t of rows) {
      const key = SCANNER_ENVELOPE_TABLE_AGE[t.table];
      if (!key || t.lastScan == null || t.lastScan <= next[key]) continue;
      next = { ...next, [key]: t.lastScan };
    }
    return next;
  });
}
