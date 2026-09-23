/** Pure helpers for the Setups board. */
import type { SetupRow } from './types';

export function fmtPx(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—';
  return v < 1 ? v.toFixed(4) : v.toFixed(2);
}

export function fmtCents(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—';
  return `${Math.round(v * 100)}¢`;
}

export function fmtR(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—';
  return `${v > 0 ? '+' : ''}${v.toFixed(2)}R`;
}

export function fmtPct(v: number | null | undefined, digits = 0): string {
  if (v == null || !Number.isFinite(v)) return '—';
  return `${v.toFixed(digits)}%`;
}

/** How far under the trigger the last price sits, as a signed cents label ("3¢ under"). */
export function distanceLabel(row: SetupRow): string {
  if (row.distance == null) return '';
  const cents = Math.round(row.distance * 100);
  if (cents <= 0) return 'at trigger';
  return `${cents}¢ under`;
}

/** The staged limit price for a proposal: the planned entry (trigger + 1c). */
export function stagedLimit(row: SetupRow): string {
  const entry = row.proposal?.entry ?? row.setup?.entry;
  return entry != null && Number.isFinite(entry) ? entry.toFixed(2) : '';
}

export function isActionable(row: SetupRow): boolean {
  return row.state === 'near' || row.state === 'armed';
}

export function rowClass(row: SetupRow): string {
  const parts = ['setups-row', `setups-row--${row.state}`];
  if (row.proposal) parts.push('setups-row--proposal');
  return parts.join(' ');
}

export function outcomeLabel(row: SetupRow): string {
  if (row.state !== 'triggered') return '';
  if (row.outcome === 'target_first') return 'Target first';
  if (row.outcome === 'stop_first') return 'Stop first';
  return 'Open';
}
