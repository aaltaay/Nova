import type { TrailEvent, TrailItem } from './types';

const KIND_LABELS: Record<string, string> = {
  place: 'Place',
  fill: 'Fill',
  flatten: 'Flatten',
  cancel: 'Cancel',
  replace: 'Replace',
  commission: 'Commission',
  close: 'Close',
};

export function formatTrailKind(kind: string | null | undefined): string {
  if (!kind) return '--';
  return KIND_LABELS[kind] || kind;
}

export function formatTrailMoney(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '--';
  const prefix = value < 0 ? '-' : '';
  return `${prefix}$${Math.abs(value).toFixed(2)}`;
}

export function formatTrailQty(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '--';
  return String(value);
}

export function formatTrailState(item: Pick<TrailItem, 'kind' | 'pnl_basis'>): string {
  if (item.kind === 'open') return 'open';
  if (item.pnl_basis === 'net') return 'closed · net';
  if (item.pnl_basis === 'gross') return 'closed · gross';
  return 'closed';
}

export function trailEventKey(event: TrailEvent, index: number): string {
  return `${event.kind}-${event.execution_id || 'journal'}-${event.ts ?? index}-${index}`;
}