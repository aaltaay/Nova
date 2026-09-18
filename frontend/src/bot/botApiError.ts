import {
  BOT_ERROR_ARM_REQUIRED,
  BOT_ERROR_NEED_API_KEY,
  BOT_ERROR_NOT_ACTIVE,
} from '../constantGroups/bot';

function detailText(body: unknown): string {
  if (!body || typeof body !== 'object') return '';
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === 'string') return detail.trim();
  if (detail && typeof detail === 'object') {
    const row = detail as { error?: unknown; reason?: unknown };
    const error = typeof row.error === 'string' ? row.error.trim() : '';
    const reason = typeof row.reason === 'string' ? row.reason.trim() : '';
    if (error && reason && error !== reason) return `${error} -- ${reason}`;
    return error || reason;
  }
  return '';
}

function isMissingApiKey(status: number, detail: string): boolean {
  if (status === 401 || status === 503) return true;
  return /nova_api_key|x-nova-api-key|api key/i.test(detail);
}

function isArmRequired(status: number, detail: string): boolean {
  if (status !== 403) return false;
  return /ARM_REQUIRED|desk Activate/i.test(detail);
}

function isNotActive(detail: string): boolean {
  return /BOT_NOT_ACTIVE|Not active -- Activate/i.test(detail);
}

export function messageFromBotApiBody(status: number, body: unknown): string {
  const detail = detailText(body);
  if (isMissingApiKey(status, detail)) return BOT_ERROR_NEED_API_KEY;
  if (isArmRequired(status, detail)) return BOT_ERROR_ARM_REQUIRED;
  if (isNotActive(detail)) return BOT_ERROR_NOT_ACTIVE;
  if (detail) return detail;
  return `bot API ${status}`;
}
