import { novaFetch } from '../api/novaFetch';
import { API_URL } from '../constantGroups/chart_api';
import { BOT_DESK_ARM_HEADER, BOT_DESK_ARM_STORAGE } from '../constantGroups/bot';
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

export function readDeskArmToken(): string {
  if (typeof localStorage === 'undefined') return '';
  return localStorage.getItem(BOT_DESK_ARM_STORAGE)?.trim() || '';
}

export function writeDeskArmToken(token: string | null): void {
  if (typeof localStorage === 'undefined') return;
  if (token) localStorage.setItem(BOT_DESK_ARM_STORAGE, token);
  else localStorage.removeItem(BOT_DESK_ARM_STORAGE);
}

function withArm(init: RequestInit = {}, armToken?: string): RequestInit {
  const headers = new Headers(init.headers);
  const token = (armToken ?? readDeskArmToken()).trim();
  if (token && !headers.has(BOT_DESK_ARM_HEADER)) {
    headers.set(BOT_DESK_ARM_HEADER, token);
  }
  return { ...init, headers };
}

export function fetchBotSession(): Promise<BotSession> {
  return novaFetch(`${BOT}/session`).then(res => readJson<BotSession>(res));
}

export function patchBotSession(body: Record<string, unknown>): Promise<BotSession> {
  return novaFetch(
    `${BOT}/session`,
    withArm({
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  ).then(res => readJson<BotSession>(res));
}

export async function armBotSession(body: Record<string, unknown> = {}): Promise<BotSession> {
  const next = await novaFetch(`${BOT}/session/arm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then(res => readJson<BotSession>(res));
  if (next.desk_arm_token) writeDeskArmToken(next.desk_arm_token);
  return next;
}

export async function disarmBotSession(): Promise<BotSession> {
  const next = await novaFetch(`${BOT}/session/disarm`, { method: 'POST' })
    .then(res => readJson<BotSession>(res));
  writeDeskArmToken(null);
  return next;
}

export function postBotAllowlist(symbol: string, op: 'add' | 'remove'): Promise<BotSession> {
  return novaFetch(`${BOT}/allowlist`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbol, op }),
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
