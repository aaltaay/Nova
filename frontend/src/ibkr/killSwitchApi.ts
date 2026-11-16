/**
 * GET / POST /api/kill-switch (D-037, ADR 025, ADR 042 D). A trip answers its
 * sweep per venue -- `sweep: [{venue, cancelled, failed, kept, error}]` -- so the page
 * can say what it cancelled where, what it could not, which venue it could
 * not read (a failed read is a failure, never "nothing to cancel"), and which
 * stops it kept resting because they protect a position (ADR 048).
 */
import { novaFetch } from '../api/novaFetch';
import { API_URL } from '../constantGroups/chart_api';
import { SAMPLE_WRITE_REFUSAL } from '../sample_data/sampleCopy';
import { onSampleDesk } from '../sample_data/sampleOrderGuard';

const KILL = `${API_URL}/kill-switch`;

/** One venue's sweep: the orders it cancelled, the ones still working, the protective stops it kept, and why it could not read. */
export type KillSweep = {
  venue: string;
  cancelled: number[];
  failed: number[];
  /** Stops kept resting because they protect a held position (ADR 048); [] from an older API. */
  kept: number[];
  error: string | null;
};

function keptIds(v: unknown): number[] {
  if (!Array.isArray(v)) return [];
  return v.flatMap((row): number[] => {
    const id = row && typeof row === 'object' ? (row as { order_id?: unknown }).order_id : row;
    return typeof id === 'number' && Number.isFinite(id) ? [id] : [];
  });
}

export type KillSwitchStatus = {
  tripped: boolean;
  reason: string | null;
  ts: number | null;
  /** Only on a trip's answer. */
  sweep?: KillSweep[];
};

function ids(v: unknown): number[] {
  return Array.isArray(v) ? v.filter((x): x is number => typeof x === 'number' && Number.isFinite(x)) : [];
}

function sweepOf(raw: Record<string, unknown>): KillSweep[] | undefined {
  if (Array.isArray(raw.sweep)) {
    return raw.sweep.flatMap((row): KillSweep[] => {
      if (!row || typeof row !== 'object') return [];
      const r = row as Record<string, unknown>;
      return [{
        venue: typeof r.venue === 'string' ? r.venue : '?',
        cancelled: ids(r.cancelled),
        failed: ids(r.failed),
        kept: keptIds(r.kept),
        error: typeof r.error === 'string' && r.error.trim() ? r.error : null,
      }];
    });
  }
  // An API before ADR 042 answers one flat list for the account it swept.
  if (Array.isArray(raw.cancelled_order_ids) || Array.isArray(raw.failed_cancel_order_ids)) {
    return [{ venue: 'account', cancelled: ids(raw.cancelled_order_ids), failed: ids(raw.failed_cancel_order_ids), kept: [], error: null }];
  }
  return undefined;
}

/** The body as the backend sent it, or null when it is not a kill-switch status. */
export function parseKillSwitch(body: unknown): KillSwitchStatus | null {
  if (!body || typeof body !== 'object') return null;
  const raw = body as Record<string, unknown>;
  if (typeof raw.tripped !== 'boolean') return null;
  const sweep = sweepOf(raw);
  return {
    tripped: raw.tripped,
    reason: typeof raw.reason === 'string' ? raw.reason : null,
    ts: typeof raw.ts === 'number' ? raw.ts : null,
    ...(sweep ? { sweep } : {}),
  };
}

async function read(res: Response): Promise<KillSwitchStatus> {
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = body && typeof body === 'object' ? (body as { detail?: unknown }).detail : null;
    throw new Error(typeof detail === 'string' ? detail : `Kill switch: HTTP ${res.status}`);
  }
  const parsed = parseKillSwitch(body);
  if (!parsed) throw new Error(`Kill switch: unreadable response (HTTP ${res.status})`);
  return parsed;
}

export async function fetchKillSwitch(): Promise<KillSwitchStatus> {
  return read(await novaFetch(KILL));
}

export async function tripKillSwitch(): Promise<KillSwitchStatus> {
  if (onSampleDesk()) throw new Error(SAMPLE_WRITE_REFUSAL);
  return read(await novaFetch(KILL, { method: 'POST' }));
}

export async function resetKillSwitch(): Promise<KillSwitchStatus> {
  if (onSampleDesk()) throw new Error(SAMPLE_WRITE_REFUSAL);
  return read(await novaFetch(`${KILL}/reset`, { method: 'POST' }));
}
