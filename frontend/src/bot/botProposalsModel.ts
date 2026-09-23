/**
 * Pure helpers for the Bots page proposals inbox: the closed setup proposals
 * the bot audit stream recorded (backend setup_scanner engine: `setup_proposal`
 * rows with outcome rearmed / disarmed / failed / triggered), the distance and
 * reward / risk line of an open one, and the dismissed ids kept for the
 * browser session.
 */
import {
  BOTS_DISMISSED_STORAGE_KEY,
  BOTS_PROPOSAL_AT,
  BOTS_PROPOSAL_CLOSED_KEEP_SEC,
  BOTS_PROPOSAL_CLOSED_LABELS,
  BOTS_PROPOSAL_CLOSED_MAX,
  BOTS_PROPOSAL_UNDER,
} from '../constantGroups/bots_page';
import type { SetupProposal, SetupRow } from '../setups/types';
import type { BotAuditEntry } from './types';

export interface ClosedProposal {
  id: string;
  symbol: string;
  kind: string | null;
  trigger: number | null;
  stop: number | null;
  status: string;
  /** "withdrawn" / "triggered". */
  label: string;
  reason: string;
  closedAt: number;
}

function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

/** Closed setup proposals from the audit stream, newest first, inside the keep window. */
export function closedProposals(audit: readonly BotAuditEntry[], nowSec: number, openIds: ReadonlySet<string>): ClosedProposal[] {
  const out: ClosedProposal[] = [];
  const seen = new Set<string>();
  const rows = [...audit].sort((a, b) => b.timestamp - a.timestamp);
  for (const row of rows) {
    if (row.action !== 'setup_proposal' || !(row.outcome in BOTS_PROPOSAL_CLOSED_LABELS)) continue;
    const inputs = row.inputs ?? {};
    const id = typeof inputs.id === 'string' ? inputs.id : '';
    const symbol = typeof inputs.symbol === 'string' ? inputs.symbol : '';
    if (!id || !symbol || seen.has(id) || openIds.has(id)) continue;
    const closedAt = num(inputs.closed_at) ?? row.timestamp;
    if (nowSec - closedAt > BOTS_PROPOSAL_CLOSED_KEEP_SEC) continue;
    seen.add(id);
    out.push({
      id,
      symbol,
      kind: typeof inputs.kind === 'string' ? inputs.kind : null,
      trigger: num(inputs.trigger),
      stop: num(inputs.stop),
      status: row.outcome,
      label: BOTS_PROPOSAL_CLOSED_LABELS[row.outcome],
      reason: row.reason ?? '',
      closedAt,
    });
    if (out.length >= BOTS_PROPOSAL_CLOSED_MAX) break;
  }
  return out;
}

const cents = (v: number) => `${Math.round(Math.abs(v) * 100)}¢`;

/** "0.03 under the trigger · <reasons> · 20¢ / 20¢" for an open proposal. */
export function proposalWhy(p: SetupProposal, row: SetupRow | undefined): string {
  const parts: string[] = [];
  const distance = row?.distance;
  if (distance != null && Number.isFinite(distance)) {
    parts.push(distance > 0 ? `${distance.toFixed(2)} ${BOTS_PROPOSAL_UNDER}` : BOTS_PROPOSAL_AT);
  }
  if (p.reasons?.length) parts.push(p.reasons.join(', '));
  if (p.trigger != null && p.target1 != null && p.stop != null) {
    parts.push(`${cents(p.target1 - p.trigger)} / ${cents(p.trigger - p.stop)}`);
  }
  return parts.join(' · ');
}

export function readDismissed(storage: Pick<Storage, 'getItem'> | null = safeSession()): Set<string> {
  try {
    const raw = storage?.getItem(BOTS_DISMISSED_STORAGE_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : null;
    return new Set(Array.isArray(parsed) ? parsed.filter((v): v is string => typeof v === 'string') : []);
  } catch {
    return new Set();
  }
}

export function writeDismissed(ids: ReadonlySet<string>, storage: Pick<Storage, 'setItem'> | null = safeSession()): void {
  try {
    storage?.setItem(BOTS_DISMISSED_STORAGE_KEY, JSON.stringify([...ids].slice(-200)));
  } catch {
    /* private mode: the dismissal lasts until the page reloads */
  }
}

function safeSession(): Storage | null {
  try {
    return typeof sessionStorage === 'undefined' ? null : sessionStorage;
  } catch {
    return null;
  }
}
