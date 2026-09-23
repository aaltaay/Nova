/** Bot audit rows as timeline lines (pure). Categories drive the Activity filter chips. */
import { BOT_ACTION_KINDS, BOT_LEVEL_LABELS } from '../constantGroups/bot';
import type { BotAuditEntry } from './types';

export type ActivityFilter = 'all' | 'proposals' | 'fired' | 'refused' | 'system';
export const ACTIVITY_FILTERS: ActivityFilter[] = ['all', 'proposals', 'fired', 'refused', 'system'];
export const ACTIVITY_FILTER_LABELS: Record<ActivityFilter, string> = {
  all: 'All',
  proposals: 'Proposals',
  fired: 'Fired',
  refused: 'Refused',
  system: 'Settings',
};

export interface ActivityLine {
  key: string;
  ts: number;
  tag: string;
  tone: 'good' | 'bad' | 'warn' | 'muted' | 'plain';
  text: string;
  note: string;
  category: Exclude<ActivityFilter, 'all'>;
}

const KINDS = new Set<string>(BOT_ACTION_KINDS);

function levelName(v: unknown): string {
  const n = Number(v);
  return BOT_LEVEL_LABELS[(n > 2 ? 2 : n) as 0 | 1 | 2] ?? String(v);
}

function sym(row: BotAuditEntry): string {
  const s = row.inputs?.symbol;
  return typeof s === 'string' ? s : '';
}

export function activityLine(row: BotAuditEntry, index: number): ActivityLine {
  const base = { key: `${row.timestamp}-${index}`, ts: Number(row.timestamp) || 0, note: row.reason ?? '' };
  const action = row.action;
  if (action === 'setup_proposal') {
    const kind = String(row.inputs?.kind ?? 'setup').replace('_', ' ');
    return { ...base, tag: 'Proposed', tone: 'good', category: 'proposals', text: `${sym(row)} ${kind}` };
  }
  if (action === 'proposal') {
    const tag = row.outcome === 'pending' ? 'Proposed' : row.outcome === 'accepted' ? 'Accepted' : 'Rejected';
    return { ...base, tag, tone: row.outcome === 'rejected' ? 'muted' : 'good', category: 'proposals',
      text: `${sym(row)} ${String(row.inputs?.kind ?? '')}`.trim() };
  }
  if (KINDS.has(action)) {
    const ok = row.outcome === 'ok';
    return { ...base, tag: ok ? 'Fired' : 'Refused', tone: ok ? 'good' : 'bad', category: ok ? 'fired' : 'refused',
      text: `${sym(row)} ${action}${row.order_id != null ? ` · order ${row.order_id}` : ''}` };
  }
  if (action === 'level') {
    return { ...base, tag: 'Level', tone: 'plain', category: 'system',
      text: `${levelName(row.inputs?.from)} → ${levelName(row.inputs?.to)}` };
  }
  if (action === 'activate' || action === 'deactivate') {
    return { ...base, tag: action === 'activate' ? 'Activated' : 'Stopped', tone: 'plain', category: 'system', text: 'from the desk' };
  }
  if (action === 'breaker_soft' || action === 'breaker_hard') {
    return { ...base, tag: 'Breaker', tone: 'bad', category: 'system', text: action === 'breaker_hard' ? '−$200 all-stop' : '−$50 bot trip' };
  }
  if (action === 'practice_rewind') {
    return { ...base, tag: 'Rewind', tone: 'muted', category: 'system', text: 'practice ledger re-read' };
  }
  if (action === 'ttl_cancel') {
    return { ...base, tag: 'Cancelled', tone: 'muted', category: 'system', text: `${sym(row)} working order past its TTL` };
  }
  return { ...base, tag: action, tone: 'muted', category: 'system', text: row.outcome };
}

export function activityLines(rows: BotAuditEntry[], filter: ActivityFilter, limit = 30): ActivityLine[] {
  const lines = rows.map(activityLine).sort((a, b) => b.ts - a.ts);
  return (filter === 'all' ? lines : lines.filter(l => l.category === filter)).slice(0, limit);
}
