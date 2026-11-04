/** The Close on a bots' row (ADR 069): POST /api/owners/close-bots {symbol} sells the bots' shares in one stock. */
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';
import { OWNER_CLOSE_BOTS_PATH } from '../constantGroups/owners';

function refusal(status: number, body: unknown): string {
  const detail = body && typeof body === 'object' ? (body as { detail?: unknown }).detail : null;
  if (typeof detail === 'string' && detail.trim()) return detail.trim();
  if (detail && typeof detail === 'object') {
    const error = (detail as { error?: unknown }).error;
    if (typeof error === 'string' && error.trim()) return error.trim();
  }
  const error = body && typeof body === 'object' ? (body as { error?: unknown }).error : null;
  if (typeof error === 'string' && error.trim()) return error.trim();
  return `The desk answered ${status}.`;
}

/** Resolves when the close was sent; rejects with the desk's own words. */
export async function closeBots(symbol: string): Promise<void> {
  const res = await novaFetch(`${API_BASE_URL}${OWNER_CLOSE_BOTS_PATH}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbol }),
  });
  const json: unknown = await res.json().catch(() => null);
  if (!res.ok) throw new Error(refusal(res.status, json));
  if (json && typeof json === 'object' && (json as { ok?: unknown }).ok === false) throw new Error(refusal(res.status, json));
}
