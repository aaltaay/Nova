/**
 * Shape checks for the bot API (QA C12 / C70, 2026-09-22; ADR 042 2026-09-30).
 *
 * The Bots page reads `session.caps.max_shares`, `session.gates`, `proposals.filter`
 * and `audit.length`. An unreadable 200, a JSON list or a `null` body used to reach
 * those reads as `{}` / `undefined` and replace the page with a raw JS error.
 * Everything the page reads is checked here, once: a malformed session is refused
 * whole (never patched up with invented caps), lists default to empty only inside
 * an otherwise sound session, and the error names the endpoint and the HTTP status
 * instead of the exception.
 *
 * ADR 042 renamed two facts and kept the old names one release: `active` (was
 * `armed`) and `ready` (was `live_fire_ready`); the sleeve's `api_kinds` (was
 * `caps.allowlist`); the day lock's `day_lock` (was `day_lock_active` /
 * `hard_lock_until_date`). Each is folded both ways here, so the page reads the
 * new name and an older reader the old one -- never one without the other.
 */
import type { BotAuditEntry, BotDayLock, BotProposal, BotSession, BotSoftBreaker } from './types';

type Loose = Record<string, unknown>;

function isPlainObject(value: unknown): value is Loose {
  return value != null && typeof value === 'object' && !Array.isArray(value);
}

const asList = (value: unknown): unknown[] => (Array.isArray(value) ? value : []);
const asStrings = (value: unknown): string[] =>
  asList(value).filter((v): v is string => typeof v === 'string');
const asNum = (value: unknown): number | null =>
  (typeof value === 'number' && Number.isFinite(value) ? value : null);
const asWhen = (value: unknown): string | number | null =>
  (typeof value === 'string' && value.trim() ? value : asNum(value));

/** "Bot session: Nova answered an unreadable response (HTTP 200)". */
export function botUnreadableMessage(label: string, status: number): string {
  return `${label}: Nova answered an unreadable response${status ? ` (HTTP ${status})` : ''}`;
}

/** String lists the page joins or searches; `working` / `setups` / `gates` are lists of rows. */
const STRING_LISTS = ['focus', 'trader_live', 'symbol_allowlist'] as const;
const ROW_LISTS = ['working', 'setups', 'gates'] as const;

function caps(raw: Loose): Loose {
  const kinds = asStrings(raw.api_kinds ?? raw.allowlist);
  return { ...raw, api_kinds: kinds, allowlist: kinds };
}

function capsByVenue(raw: unknown): Record<string, Loose> | undefined {
  if (!isPlainObject(raw)) return undefined;
  const out: Record<string, Loose> = {};
  for (const [venue, value] of Object.entries(raw)) {
    if (isPlainObject(value)) out[venue] = caps(value);
  }
  return out;
}

function deactivated(raw: unknown): Loose | null {
  if (!isPlainObject(raw) || typeof raw.reason !== 'string') return null;
  return { at: asNum(raw.at), reason: raw.reason, text: typeof raw.text === 'string' ? raw.text : null };
}

/** The desk venue's day lock: the new block, else the legacy pair it replaced. */
function dayLock(body: Loose): BotDayLock {
  const raw = body.day_lock;
  if (isPlainObject(raw)) {
    return {
      active: raw.active === true,
      until: asWhen(raw.until),
      tripped_at: asWhen(raw.tripped_at),
      pnl: asNum(raw.pnl),
      venue: typeof raw.venue === 'string' ? raw.venue : null,
    };
  }
  return {
    active: body.day_lock_active === true,
    until: asWhen(body.hard_lock_until_date),
    tripped_at: null,
    pnl: null,
    venue: null,
  };
}

function softBreaker(body: Loose): BotSoftBreaker {
  const raw = body.soft_breaker;
  if (isPlainObject(raw)) {
    return { fired: raw.fired === true, at: asWhen(raw.at), pnl: asNum(raw.pnl), until: asWhen(raw.until) };
  }
  return { fired: body.soft_breaker_fired === true, at: null, pnl: null, until: null };
}

function entriesToday(raw: unknown): Loose | undefined {
  if (!isPlainObject(raw)) return undefined;
  const count = asNum(raw.count);
  const cap = asNum(raw.cap);
  if (count == null || cap == null) return undefined;
  return {
    count,
    cap,
    venue_day: typeof raw.venue_day === 'string' ? raw.venue_day : null,
    entries: asList(raw.entries).filter(isPlainObject),
    approved: asNum(raw.approved) ?? 0,
  };
}

/** The session the Bots page can render, or null when the body is not one. */
export function parseBotSession(body: unknown): BotSession | null {
  if (!isPlainObject(body) || !isPlainObject(body.caps)) return null;
  const active = typeof body.active === 'boolean' ? body.active : body.armed === true;
  const ready = typeof body.ready === 'boolean' ? body.ready : body.live_fire_ready === true;
  const lock = dayLock(body);
  const soft = softBreaker(body);
  const out: Loose = {
    ...body,
    caps: caps(body.caps),
    active,
    armed: active,
    ready,
    live_fire_ready: ready,
    ready_reason: typeof body.ready_reason === 'string' ? body.ready_reason : null,
    deactivated: deactivated(body.deactivated),
    day_lock: lock,
    day_lock_active: lock.active,
    hard_lock_until_date: typeof body.hard_lock_until_date === 'string' ? body.hard_lock_until_date : null,
    soft_breaker: soft,
    soft_breaker_fired: soft.fired,
  };
  const byVenue = capsByVenue(body.caps_by_venue);
  if (byVenue) out.caps_by_venue = byVenue;
  else delete out.caps_by_venue;
  const entries = entriesToday(body.entries_today);
  if (entries) out.entries_today = entries;
  else delete out.entries_today;
  if (!isPlainObject(body.caps_bounds)) delete out.caps_bounds;
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
