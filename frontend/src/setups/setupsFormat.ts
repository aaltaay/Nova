/** Pure helpers for the Setups board. */
import { CATALYST_CATEGORY_LABELS, CATALYST_VERDICT_TITLES } from '../constants';
import type { SetupPillars, SetupRow } from './types';

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

/** The grade cell's tooltip: what the News pillar rested on (ADR 024). */
export function catalystTitle(p: SetupPillars | null | undefined): string {
  const c = p?.catalyst;
  if (!c) return 'Catalyst: not read when this armed (unknown, not a fail)';
  const pending = c.news_pending ? `News pending: halted ${c.halt_code ?? ''} for news\n` : '';
  const checked = c.sources_answered?.length ? `\nChecked: ${c.sources_answered.join(', ')}` : '';
  const head = CATALYST_VERDICT_TITLES[c.verdict] ?? c.verdict;
  if (c.verdict !== 'catalyst' && c.verdict !== 'negative') return `${pending}${head}${checked}`;
  const cat = c.category ? (CATALYST_CATEGORY_LABELS[c.category] ?? c.category) : '';
  const strength = c.strength ? ` (${c.strength})` : '';
  const dilution = c.negative_too ? '\nAlso: an offering / dilution item' : '';
  const via = c.source ? ` via ${c.source}` : '';
  return `${pending}${head}: ${cat}${strength}${via}${c.title ? `\n${c.title}` : ''}${dilution}${checked}`;
}
