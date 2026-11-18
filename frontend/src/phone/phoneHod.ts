/**
 * The HOD Momo and Running Up lists as the phone's Scan draws them (mockup v1, 2026-11-18). Pure.
 *
 * The rows are the desk's: the same feed, split into its two lists and folded to one row per stock by the
 * desk's own functions (`hod_momo/scannerPartition`, `collapseAlertsBySymbol`), so a stock keeps the place
 * and the time of its first alert today and shows the price of its newest. This file only words a row for
 * a column a few characters wide.
 */
import { collapseAlertsBySymbol } from '../hod_momo/collapseAlertsBySymbol';
import { fmtStripClock, stripAlertMs } from '../hod_momo/hodMomoStripRows';
import { partitionScannerAlerts } from '../hod_momo/scannerPartition';
import type { AlertObject } from '../hod_momo/types';

export type PhoneHodList = 'hod_momo' | 'running_up';

export interface PhoneHodRow {
  symbol: string;
  /** When the stock first alerted today, "HH:MM" ET. */
  at: string;
  /** The same moment in epoch ms; null when the alert carries no readable time. */
  atMs: number | null;
  /** The newest alert's strategy, in a few words. */
  strategy: string;
  /** How many alerts the stock has raised on this list today. */
  count: number;
  price: number | null;
  /** The change at the newest alert, as a fraction; null when the alert had none. */
  change: number | null;
  volume: number | null;
  rvol: number | null;
  float: number | null;
}

/** The desk's strategy names, cut to what fits under a ticker chip. An id not listed keeps the desk's name. */
const SHORT_NAME: Readonly<Record<number, string>> = {
  1: 'Former momo',
  2: '52-week breakout',
  3: 'Low float, RVol',
  4: 'Low float, $20+',
  5: 'Low float mover',
  6: 'Mid float, RVol',
  7: 'Low float, RVol',
  8: 'Mid float, $20+',
  9: 'Mid float, $20+',
  10: 'Up 10% / 10m',
  11: 'Up 5% / 5m',
  12: 'Running up',
  13: 'Near the high',
};

export function hodShortName(strategyId: number, name: string): string {
  return SHORT_NAME[strategyId] ?? name;
}

/** `alerts` newest first, as the feed sends them. One row per stock, the newest first catch on top. */
export function phoneHodRows(alerts: readonly AlertObject[], list: PhoneHodList): PhoneHodRow[] {
  const parts = partitionScannerAlerts(alerts as AlertObject[]);
  const mine = list === 'running_up' ? parts.runningUp : parts.hodMomentum;
  const counts = new Map<string, number>();
  for (const a of mine) counts.set(a.ticker, (counts.get(a.ticker) ?? 0) + 1);
  // The collapse writes on its rows: hand it copies, never the feed's own objects.
  return collapseAlertsBySymbol(mine.map((a) => ({ ...a }))).map((row) => ({
    symbol: row.ticker,
    at: fmtStripClock(row).slice(0, 5),
    atMs: stripAlertMs(row),
    strategy: hodShortName(row.strategy_id, row.strategy_name),
    count: counts.get(row.ticker) ?? 1,
    price: Number.isFinite(row.price) ? row.price : null,
    change: row.change_pct == null || !Number.isFinite(row.change_pct) ? null : row.change_pct / 100,
    volume: row.volume,
    rvol: row.rvol,
    float: row.float_shares,
  }));
}

/** A stock that first alerted in the last two minutes: the row the eye should find. */
export const HOD_NEW_MS = 120_000;

export function hodRowIsNew(row: Pick<PhoneHodRow, 'atMs'>, nowMs: number): boolean {
  return row.atMs != null && nowMs - row.atMs >= 0 && nowMs - row.atMs < HOD_NEW_MS;
}
