/**
 * A bot API refusal in the backend's own words. The bot routes and the stock-mode
 * rules answer `{detail: {reason, error, field}}`: `error` is the sentence, `reason`
 * a code (BOT_LIVE_NOT_BUILT, STOCK_MODE_LIVE, ...). The page shows the sentence;
 * a code adds nothing the operator can act on, so it is dropped. Two answers have
 * their own words here: a missing API key, and a bot that is not active.
 */
import {
  BOT_ERROR_ARM_REQUIRED,
  BOT_ERROR_NEED_API_KEY,
  BOT_ERROR_NOT_ACTIVE,
} from '../constantGroups/bot';

/** An UPPER_SNAKE refusal code, as opposed to a sentence. */
const CODE = /^[A-Z][A-Z0-9_]+$/;

function detailText(body: unknown): string {
  if (!body || typeof body !== 'object') return '';
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === 'string') return detail.trim();
  if (detail && typeof detail === 'object') {
    const row = detail as { error?: unknown; reason?: unknown; detail?: unknown };
    const error = typeof row.error === 'string' ? row.error.trim()
      : typeof row.detail === 'string' ? row.detail.trim() : '';
    const reason = typeof row.reason === 'string' ? row.reason.trim() : '';
    if (error && reason && error !== reason && !CODE.test(reason)) return `${error} -- ${reason}`;
    return error || reason;
  }
  return '';
}

function reasonCode(body: unknown): string {
  const detail = body && typeof body === 'object' ? (body as { detail?: unknown }).detail : null;
  if (detail && typeof detail === 'object') {
    const row = detail as { reason?: unknown; code?: unknown };
    if (typeof row.reason === 'string') return row.reason;
    if (typeof row.code === 'string') return row.code;
  }
  const code = body && typeof body === 'object' ? (body as { code?: unknown }).code : null;
  return typeof code === 'string' ? code : '';
}

function isMissingApiKey(status: number, detail: string): boolean {
  if (status === 401 || status === 503) return true;
  return /nova_api_key|x-nova-api-key|api key/i.test(detail);
}

function isArmRequired(status: number, detail: string, code: string): boolean {
  if (status !== 403) return false;
  return code === 'BOT_ARM_REQUIRED' || /ARM_REQUIRED|desk Activate|Activate token/i.test(detail);
}

function isNotActive(detail: string, code: string): boolean {
  return code === 'BOT_NOT_ACTIVE' || /BOT_NOT_ACTIVE|Not active -- Activate/i.test(detail);
}

export function messageFromBotApiBody(status: number, body: unknown): string {
  const detail = detailText(body);
  const code = reasonCode(body);
  if (isMissingApiKey(status, detail)) return BOT_ERROR_NEED_API_KEY;
  if (isArmRequired(status, detail, code)) return BOT_ERROR_ARM_REQUIRED;
  if (isNotActive(detail, code)) return BOT_ERROR_NOT_ACTIVE;
  if (detail) return detail;
  return `bot API ${status}`;
}
