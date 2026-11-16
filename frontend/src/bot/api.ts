/**
 * The bot API reads that stay after ADR 072 retired the bots: `GET /api/bot/session` (the day cover the alarms read)
 * and `GET /api/bot/audit` (history kept on disk). Every write the Bots page made -- level, arm, switch, keys,
 * allowlist, proposals, focus -- went with its route.
 */
import { novaFetch } from '../api/novaFetch';
import { API_URL } from '../constantGroups/chart_api';
import { BOT_LABEL_AUDIT, BOT_LABEL_SESSION } from '../constantGroups/bot';
import { botApiError } from './botApiError';
import { botUnreadableMessage, parseBotAudit, parseBotSession } from './botPayload';
import type { BotAuditEntry, BotSession } from './types';

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
    throw botApiError(res.status, body === UNREADABLE ? {} : body);
  }
  if (body === UNREADABLE) throw new Error(botUnreadableMessage(label, res.status));
  return body;
}

function required<T>(parsed: T | null, label: string, res: Response): T {
  if (parsed == null) throw new Error(botUnreadableMessage(label, res.status));
  return parsed;
}

export async function fetchBotSession(): Promise<BotSession> {
  const res = await novaFetch(`${BOT}/session`);
  return required(parseBotSession(await readJson(res, BOT_LABEL_SESSION)), BOT_LABEL_SESSION, res);
}

export async function fetchBotAudit(limit = 40): Promise<BotAuditEntry[]> {
  const res = await novaFetch(`${BOT}/audit?limit=${limit}`);
  return required(parseBotAudit(await readJson(res, BOT_LABEL_AUDIT)), BOT_LABEL_AUDIT, res);
}
