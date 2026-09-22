/**
 * One read of /api/ibkr/status into the shape every desk surface assumes
 * (QA C1 / C4, 2026-09-22).
 *
 * The poller used to cast the JSON straight to IbkrStatus. A backend built
 * between 81972619 and 58c1fbc2 sent `capture_resume` / `capture_stopped` as
 * one object; any version could send a non-string `account_id`. The header's
 * recording signals and account pill then called `.filter` / `.trim` on them
 * and the app-shell boundary replaced the whole desk. Normalising here, once,
 * means no consumer has to guard: a field that is present but malformed
 * becomes the empty value of its type; a field that is absent stays absent;
 * a well-formed payload comes back unchanged.
 */
import type { IbkrMode, IbkrStatus } from './types';

const MODES: readonly IbkrMode[] = ['paper', 'live', 'sim', 'disconnected'];
const VENUES = ['live', 'paper', 'sim'] as const;
const GATEWAY_MODES = ['paper', 'live'] as const;

/** String-or-null fields consumers call string methods on. */
const NULLABLE_STRING_FIELDS = [
  'account_id',
  'capture_symbol',
  'capture_error',
  'spend_locked_reason',
  'spend_permitted_reason',
  'trading_allowed_reason',
  'disconnect_hint',
] as const;

/** Optional string fields: dropped when present but not a string. */
const OPTIONAL_STRING_FIELDS = [
  'session_reason',
  'session_state',
  'spend_status',
  'spend_permitted_status',
  'broker_account_kind',
] as const;

/** Lists of per-symbol rows: only objects that name a symbol survive. */
const ROW_LIST_FIELDS = ['capture_sessions', 'capture_resume', 'capture_stopped'] as const;

/** Lists of plain strings (symbols, account ids). */
const STRING_LIST_FIELDS = ['capture_symbols', 'account_ids'] as const;

type Loose = Record<string, unknown>;

function isPlainObject(value: unknown): value is Loose {
  return value != null && typeof value === 'object' && !Array.isArray(value);
}

function oneOf<T extends string>(value: unknown, allowed: readonly T[]): value is T {
  return typeof value === 'string' && (allowed as readonly string[]).includes(value);
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : [];
}

function rowList(value: unknown): Loose[] {
  return Array.isArray(value)
    ? value.filter((row): row is Loose => isPlainObject(row) && typeof row.symbol === 'string')
    : [];
}

/** A status payload in the shape the desk reads, or null when the body is not an object at all. */
export function normalizeIbkrStatus(raw: unknown): IbkrStatus | null {
  if (!isPlainObject(raw)) return null;
  const out: Loose = { ...raw };
  out.connected = raw.connected === true;
  if (!oneOf(raw.mode, MODES)) out.mode = 'disconnected';
  if ('venue' in raw && !oneOf(raw.venue, VENUES)) delete out.venue;
  if ('gateway_mode' in raw && !oneOf(raw.gateway_mode, GATEWAY_MODES)) delete out.gateway_mode;
  if ('intentional_gateway_mode' in raw && !oneOf(raw.intentional_gateway_mode, GATEWAY_MODES)) {
    out.intentional_gateway_mode = null;
  }
  for (const key of NULLABLE_STRING_FIELDS) {
    if (key in raw && typeof raw[key] !== 'string') out[key] = null;
  }
  for (const key of OPTIONAL_STRING_FIELDS) {
    if (key in raw && typeof raw[key] !== 'string') delete out[key];
  }
  for (const key of STRING_LIST_FIELDS) {
    if (key in raw) out[key] = stringList(raw[key]);
  }
  for (const key of ROW_LIST_FIELDS) {
    if (key in raw) out[key] = rowList(raw[key]);
  }
  if ('gateway_self_heal' in raw && !isPlainObject(raw.gateway_self_heal)) out.gateway_self_heal = null;
  return out as unknown as IbkrStatus;
}
