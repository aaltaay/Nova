import type { ActivityRow } from './types';

export function formatActivityOrderRef(
  row: Pick<ActivityRow, 'order_id' | 'perm_id'>,
): string {
  const sessionId = Number(row.order_id);
  if (Number.isFinite(sessionId) && sessionId > 0) {
    return String(Math.trunc(sessionId));
  }
  const permId = Number(row.perm_id);
  if (Number.isFinite(permId) && permId > 0) {
    return String(Math.trunc(permId));
  }
  return '--';
}

export function formatActivityQty(row: Pick<ActivityRow, 'requested_qty' | 'sent_qty'>): string {
  const requested = row.requested_qty;
  const sent = row.sent_qty;
  if (requested == null && sent == null) return '--';
  if (requested == null) return String(sent);
  if (sent == null) return String(requested);
  if (requested === sent) return String(sent);
  return `${requested} -> ${sent}`;
}

export function formatActivityTime(ts: number | null | undefined): string {
  if (ts == null || !Number.isFinite(ts) || ts <= 0) return '--';
  return new Date(ts * 1000).toLocaleTimeString();
}

export function formatTimingMs(ms: number | null | undefined): string {
  if (ms == null || !Number.isFinite(ms)) return '--';
  return `${ms.toFixed(1)}ms`;
}
