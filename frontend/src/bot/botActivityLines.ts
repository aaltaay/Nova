/**
 * The Bots page timeline as lines (pure): the bot audit stream (proposals,
 * fires and refusals, level changes, breakers) and the setup scanner's own
 * record of the day (armed, near, triggered, failed, scored -- setups.db).
 * Categories drive the Activity filter chips; scanner events show under All.
 */
import { BOT_ACTION_KINDS, BOT_LEVEL_LABELS } from '../constantGroups/bot';
import { SETUP_KIND_LABELS } from '../constantGroups/setups';
import type { SetupStoreRow } from '../setups/useSetupRows';
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

export type ActivityTone = 'good' | 'bad' | 'warn' | 'accent' | 'violet' | 'muted' | 'plain';

export interface ActivityLine {
  key: string;
  ts: number;
  tag: string;
  tone: ActivityTone;
  text: string;
  note: string;
  category: Exclude<ActivityFilter, 'all'> | 'scanner';
}

const KINDS = new Set<string>(BOT_ACTION_KINDS);
const WITHDRAWN = new Set(['rearmed', 'disarmed', 'failed']);
const VERDICT_TAGS: Record<string, [string, ActivityTone]> = {
  go: ['Go', 'good'],
  wait: ['Wait', 'warn'],
  veto: ['No', 'bad'],
  blind: ['Blind', 'muted'],
};

function levelName(v: unknown): string {
  const n = Number(v);
  return BOT_LEVEL_LABELS[(n > 2 ? 2 : n) as 0 | 1 | 2] ?? String(v);
}

function sym(row: BotAuditEntry): string {
  const s = row.inputs?.symbol;
  return typeof s === 'string' ? s : '';
}

function kindName(kind: unknown): string {
  const k = typeof kind === 'string' ? kind : 'setup';
  return (SETUP_KIND_LABELS[k] ?? k.replace(/_/g, ' ')).toLowerCase();
}

function px(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—';
  return v < 1 ? v.toFixed(4) : v.toFixed(2);
}

/** One audit row as a line; null for a row the setup scanner's own record already draws. */
export function activityLine(row: BotAuditEntry, index: number): ActivityLine | null {
  const base = { key: `a-${row.timestamp}-${index}`, ts: Number(row.timestamp) || 0, note: row.reason ?? '' };
  const action = row.action;
  if (action === 'setup_proposal') {
    const what = `${sym(row)} ${kindName(row.inputs?.kind)}`.trim();
    if (WITHDRAWN.has(row.outcome)) {
      return { ...base, tag: 'Withdrawn', tone: 'muted', category: 'proposals', text: `${sym(row)} proposal` };
    }
    // A proposal closed by its trigger is the setup's Triggered line (setups.db).
    if (row.outcome === 'triggered') return null;
    const tape = row.inputs?.tape_now;
    const grade = row.inputs?.grade;
    const note = [typeof tape === 'string' ? `tape ${tape}` : '', typeof grade === 'string' ? `grade ${grade}` : '']
      .filter(Boolean).join(' · ');
    return { ...base, tag: 'Proposed', tone: 'good', category: 'proposals', text: what, note: note || base.note };
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
      text: `${levelName(row.inputs?.from)} → ${levelName(row.inputs?.to)}`, note: base.note || 'from the desk' };
  }
  if (action === 'activate' || action === 'deactivate') {
    return { ...base, tag: action === 'activate' ? 'Activated' : 'Stopped', tone: 'accent', category: 'system', text: 'the bot', note: 'from the desk' };
  }
  if (action === 'breaker_soft' || action === 'breaker_hard') {
    return { ...base, tag: 'Breaker', tone: 'bad', category: 'system', text: action === 'breaker_hard' ? '−$200 all-stop' : '−$50 bot trip' };
  }
  if (action === 'practice_rewind') {
    return { ...base, tag: 'Rewind', tone: 'violet', category: 'system', text: 'practice ledger re-read', note: base.note || 'Sim playhead scrubbed back' };
  }
  if (action === 'ttl_cancel') {
    return { ...base, tag: 'Cancelled', tone: 'muted', category: 'system', text: `${sym(row)} working order past its TTL` };
  }
  return { ...base, tag: action, tone: 'muted', category: 'system', text: row.outcome };
}

/** The day's setup scanner events, one line per moment each setup reached. */
export function setupActivityLines(rows: readonly SetupStoreRow[]): ActivityLine[] {
  const out: ActivityLine[] = [];
  for (const r of rows) {
    const k = (suffix: string) => `s-${r.id}-${suffix}`;
    if (r.armed_at) {
      const bars = r.pullback_bars ?? 0;
      const note = [
        bars ? `${bars} red candle${bars === 1 ? '' : 's'} held the 9 EMA` : '',
        r.leg_pct != null ? `leg +${(r.leg_pct * 100).toFixed(1)}%` : '',
        r.grade ? `grade ${r.grade}` : '',
      ].filter(Boolean).join(' · ');
      out.push({ key: k('armed'), ts: r.armed_at, tag: 'Armed', tone: 'accent', category: 'scanner',
        text: `${r.symbol} · trigger ${px(r.trigger)} · stop ${px(r.stop)}`, note });
    }
    if (r.near_at) {
      const verdict = r.near_tape?.verdict ?? '';
      const [tag, tone] = VERDICT_TAGS[verdict] ?? ['Near', 'plain'];
      out.push({ key: k('near'), ts: r.near_at, tag, tone, category: 'scanner',
        text: `${r.symbol} near ${px(r.trigger)}`, note: (r.near_tape?.reasons ?? []).join(', ') });
    }
    if (r.triggered_at) {
      const verdict = r.trigger_tape?.verdict;
      out.push({ key: k('triggered'), ts: r.triggered_at, tag: 'Triggered', tone: 'good', category: 'scanner',
        text: `${r.symbol} at ${px(r.entry ?? r.trigger)}${verdict ? ` · tape ${verdict}` : ''}`,
        note: (r.trigger_tape?.reasons ?? []).join(', ') });
    }
    if (r.failed_at) {
      out.push({ key: k('failed'), ts: r.failed_at, tag: 'Failed', tone: 'bad', category: 'scanner',
        text: r.symbol, note: r.fail_reason ?? r.reason ?? '' });
    }
    if (r.disarmed_at) {
      out.push({ key: k('disarmed'), ts: r.disarmed_at, tag: 'Disarmed', tone: 'muted', category: 'scanner',
        text: r.symbol, note: r.reason ?? '' });
    }
    if (r.outcome_at && (r.outcome === 'target_first' || r.outcome === 'stop_first')) {
      out.push({ key: k('scored'), ts: r.outcome_at, tag: 'Scored', tone: r.outcome === 'target_first' ? 'good' : 'bad',
        category: 'scanner', text: `${r.symbol} ${r.outcome === 'target_first' ? 'target first' : 'stop first'}`,
        note: r.bar_r != null ? `${r.bar_r > 0 ? '+' : ''}${r.bar_r.toFixed(2)}R under the research exits` : '' });
    }
  }
  return out;
}

export function activityLines(
  rows: BotAuditEntry[],
  filter: ActivityFilter,
  limit = 30,
  setupRows: readonly SetupStoreRow[] = [],
): ActivityLine[] {
  const audit = rows.map(activityLine).filter((l): l is ActivityLine => l != null);
  const lines = [...audit, ...setupActivityLines(setupRows)].sort((a, b) => b.ts - a.ts);
  return (filter === 'all' ? lines : lines.filter(l => l.category === filter)).slice(0, limit);
}
