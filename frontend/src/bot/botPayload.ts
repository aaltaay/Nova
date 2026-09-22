/**
 * Shape checks for the bot API (QA C12 / C70, 2026-09-22).
 *
 * The Bots page reads `session.caps.max_shares`, `session.trader_live.join`,
 * `proposals.filter` and `audit.length`. An unreadable 200, a JSON list or a
 * `null` body used to reach those reads as `{}` / `undefined` and replace the
 * page with a raw JS error. Everything the page reads is checked here, once:
 * a malformed session is refused whole (never patched up with invented
 * caps), lists default to empty only inside an otherwise sound session, and
 * the error names the endpoint and the HTTP status instead of the exception.
 */
import type { BotAuditEntry, BotProposal, BotSession } from './types';

type Loose = Record<string, unknown>;

function isPlainObject(value: unknown): value is Loose {
  return value != null && typeof value === 'object' && !Array.isArray(value);
}

const asList = (value: unknown): unknown[] => (Array.isArray(value) ? value : []);
const asStrings = (value: unknown): string[] =>
  asList(value).filter((v): v is string => typeof v === 'string');

/** "Bot session: Nova answered an unreadable response (HTTP 200)". */
export function botUnreadableMessage(label: string, status: number): string {
  return `${label}: Nova answered an unreadable response${status ? ` (HTTP ${status})` : ''}`;
}

/** String lists the page joins or searches; `working` / `packs` are lists of rows. */
const STRING_LISTS = ['focus', 'trader_live', 'symbol_allowlist'] as const;
const ROW_LISTS = ['working', 'packs'] as const;

/** The session the Bots page can render, or null when the body is not one. */
export function parseBotSession(body: unknown): BotSession | null {
  if (!isPlainObject(body) || !isPlainObject(body.caps) || !isPlainObject(body.advise)) return null;
  const out: Loose = { ...body, caps: { ...body.caps, allowlist: asStrings(body.caps.allowlist) } };
  // Required lists default to empty; optional ones stay absent when absent.
  for (const key of STRING_LISTS) {
    if (key in body || key !== 'symbol_allowlist') out[key] = asStrings(body[key]);
  }
  for (const key of ROW_LISTS) {
    if (key in body || key === 'working') out[key] = asList(body[key]).filter(isPlainObject);
  }
  return out as unknown as BotSession;
}

/** `{proposals: [...]}` -> the rows, or null when the container is wrong. */
export function parseBotProposals(body: unknown): BotProposal[] | null {
  if (!isPlainObject(body) || !Array.isArray(body.proposals)) return null;
  return body.proposals.filter(isPlainObject) as unknown as BotProposal[];
}

/** `{entries: [...]}` -> the rows, or null when the container is wrong. */
export function parseBotAudit(body: unknown): BotAuditEntry[] | null {
  if (!isPlainObject(body) || !Array.isArray(body.entries)) return null;
  return body.entries.filter(isPlainObject) as unknown as BotAuditEntry[];
}
