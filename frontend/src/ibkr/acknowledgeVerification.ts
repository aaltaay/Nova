import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';

export async function acknowledgeIbkrVerification(
  symbol: string,
): Promise<boolean> {
  const normalized = symbol.trim().toUpperCase();
  if (!normalized) return false;
  const response = await novaFetch(
    `${API_BASE_URL}/api/ibkr/verification/${encodeURIComponent(normalized)}/acknowledge`,
    { method: 'POST' },
  );
  if (!response.ok) return false;
  const body = await response.json() as { ok?: boolean };
  return body.ok === true;
}
