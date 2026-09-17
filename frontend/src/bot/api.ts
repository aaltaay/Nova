import { novaFetch } from '../api/novaFetch';
import { API_URL } from '../constantGroups/chart_api';
import type { BotAuditEntry, BotProposal, BotSession } from './types';

const BOT = `${API_URL}/bot`;

async function readJson<T>(res: Response): Promise<T> {
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (body as { detail?: { error?: string; reason?: string } }).detail;
    throw new Error(detail?.error || detail?.reason || `bot API ${res.status}`);
  }
  return body as T;
}

export function fetchBotSession(): Promise<BotSession> {
  return novaFetch(`${BOT}/session`).then(res => readJson<BotSession>(res));
}

export function patchBotSession(body: Record<string, unknown>): Promise<BotSession> {
  return novaFetch(`${BOT}/session`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then(res => readJson<BotSession>(res));
}

export function fetchBotProposals(): Promise<BotProposal[]> {
  return novaFetch(`${BOT}/proposals`)
    .then(res => readJson<{ proposals: BotProposal[] }>(res))
    .then(body => body.proposals);
}

export function resolveProposal(id: string, action: 'accept' | 'reject'): Promise<BotProposal> {
  return novaFetch(`${BOT}/proposals/${id}/${action}`, { method: 'POST' })
    .then(res => readJson<BotProposal>(res));
}

export function fetchBotAudit(limit = 40): Promise<BotAuditEntry[]> {
  return novaFetch(`${BOT}/audit?limit=${limit}`)
    .then(res => readJson<{ entries: BotAuditEntry[] }>(res))
    .then(body => body.entries);
}

export function syncTraderLive(live: string[]): Promise<void> {
  void novaFetch(`${BOT}/focus/sync`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ live }),
  }).catch(() => {
    /* Eyes stay honest on the next successful sync */
  });
  return Promise.resolve();
}
