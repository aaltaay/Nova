/** GET / POST /api/kill-switch (D-037, ADR 025). */
import { novaFetch } from '../api/novaFetch';
import { API_URL } from '../constantGroups/chart_api';
import { SAMPLE_WRITE_REFUSAL } from '../sample_data/sampleCopy';
import { onSampleDesk } from '../sample_data/sampleOrderGuard';

const KILL = `${API_URL}/kill-switch`;

export type KillSwitchStatus = {
  tripped: boolean;
  reason: string | null;
  ts: number | null;
};

/** The body as the backend sent it, or null when it is not a kill-switch status. */
export function parseKillSwitch(body: unknown): KillSwitchStatus | null {
  if (!body || typeof body !== 'object') return null;
  const raw = body as Record<string, unknown>;
  if (typeof raw.tripped !== 'boolean') return null;
  return {
    tripped: raw.tripped,
    reason: typeof raw.reason === 'string' ? raw.reason : null,
    ts: typeof raw.ts === 'number' ? raw.ts : null,
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
