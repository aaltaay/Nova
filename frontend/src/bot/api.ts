import { novaFetch } from '../api/novaFetch';
import { API_URL } from '../constantGroups/chart_api';
import {
  BOT_DESK_ARM_HEADER,
  BOT_DESK_ARM_STORAGE,
  BOT_LABEL_AUDIT,
  BOT_LABEL_PROPOSALS,
  BOT_LABEL_SESSION,
} from '../constantGroups/bot';
import { SAMPLE_WRITE_REFUSAL } from '../sample_data/sampleCopy';
import { onSampleDesk } from '../sample_data/sampleOrderGuard';
import { messageFromBotApiBody } from './botApiError';
import { botUnreadableMessage, parseBotAudit, parseBotProposals, parseBotSession } from './botPayload';
import type { BotAuditEntry, BotProposal, BotSession } from './types';

const BOT = `${API_URL}/bot`;

const UNREADABLE = Symbol('unreadable');

/**
 * The parsed body of a bot API answer. A non-2xx throws the backend's own
 * words; a 2xx whose body does not parse throws an "unreadable response"
 * error naming the endpoint -- never `{}`, which let the Bots page read
 * `undefined.caps` (QA C12 / C70).
 */
async function readJson(res: Response, label: string): Promise<unknown> {
  const body: unknown = await res.json().catch(() => UNREADABLE);
  if (!res.ok) {
    throw new Error(messageFromBotApiBody(res.status, body === UNREADABLE ? {} : body));
  }
  if (body === UNREADABLE) throw new Error(botUnreadableMessage(label, res.status));
  return body;
}

function required<T>(parsed: T | null, label: string, res: Response): T {
  if (parsed == null) throw new Error(botUnreadableMessage(label, res.status));
  return parsed;
}

/** V4: bot controls change the live desk, so the sample desk refuses them before any request. */
function refuseOnSampleDesk(): void {
  if (onSampleDesk()) throw new Error(SAMPLE_WRITE_REFUSAL);
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

export async function fetchBotSession(): Promise<BotSession> {
  const res = await novaFetch(`${BOT}/session`);
  return required(parseBotSession(await readJson(res, BOT_LABEL_SESSION)), BOT_LABEL_SESSION, res);
}

export async function patchBotSession(body: Record<string, unknown>): Promise<BotSession> {
  refuseOnSampleDesk();
  const res = await novaFetch(
    `${BOT}/session`,
    withArm({
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  );
  return (await readJson(res, BOT_LABEL_SESSION)) as BotSession;
}

export async function armBotSession(body: Record<string, unknown> = {}): Promise<BotSession> {
  refuseOnSampleDesk();
  const res = await novaFetch(`${BOT}/session/arm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const next = (await readJson(res, BOT_LABEL_SESSION)) as BotSession;
  if (next.desk_arm_token) writeDeskArmToken(next.desk_arm_token);
  return next;
}

export async function disarmBotSession(): Promise<BotSession> {
  refuseOnSampleDesk();
  const res = await novaFetch(`${BOT}/session/disarm`, { method: 'POST' });
  const next = (await readJson(res, BOT_LABEL_SESSION)) as BotSession;
  writeDeskArmToken(null);
  return next;
}

export async function postBotAllowlist(symbol: string, op: 'add' | 'remove'): Promise<BotSession> {
  refuseOnSampleDesk();
  const res = await novaFetch(`${BOT}/allowlist`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbol, op }),
  });
  return (await readJson(res, BOT_LABEL_SESSION)) as BotSession;
}

export async function fetchBotProposals(): Promise<BotProposal[]> {
  const res = await novaFetch(`${BOT}/proposals`);
  return required(parseBotProposals(await readJson(res, BOT_LABEL_PROPOSALS)), BOT_LABEL_PROPOSALS, res);
}

export async function resolveProposal(id: string, action: 'accept' | 'reject'): Promise<BotProposal> {
  refuseOnSampleDesk();
  const res = await novaFetch(`${BOT}/proposals/${id}/${action}`, { method: 'POST' });
  return (await readJson(res, BOT_LABEL_PROPOSALS)) as BotProposal;
}

export async function fetchBotAudit(limit = 40): Promise<BotAuditEntry[]> {
  const res = await novaFetch(`${BOT}/audit?limit=${limit}`);
  return required(parseBotAudit(await readJson(res, BOT_LABEL_AUDIT)), BOT_LABEL_AUDIT, res);
}

/**
 * The Trader's live L2 tabs, so bot Eyes share the max-3 cap. Never from the
 * sample desk: its empty list used to overwrite the live bot's (V4).
 */
export function syncTraderLive(live: string[]): Promise<void> {
  if (onSampleDesk()) return Promise.resolve();
  void novaFetch(`${BOT}/focus/sync`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ live }),
  }).catch((err) => {
    // Eyes stay honest on the next successful sync.
    console.warn('[Nova] bot focus sync failed', err);
  });
  return Promise.resolve();
}
