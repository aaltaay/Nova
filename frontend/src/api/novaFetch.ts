/**
 * fetch wrapper that attaches X-Nova-Api-Key when VITE_NOVA_API_KEY is set.
 * Local loopback APIs without a key need no header (backend auth.py).
 */
import { NOVA_API_KEY_HEADER } from '../constantGroups/api_auth';

function resolveApiKey(): string {
  const fromEnv = (import.meta.env.VITE_NOVA_API_KEY as string | undefined)?.trim();
  if (fromEnv) return fromEnv;
  if (typeof localStorage !== 'undefined') {
    const fromStorage = localStorage.getItem('nova_api_key')?.trim();
    if (fromStorage) return fromStorage;
  }
  return '';
}

export function novaFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const key = resolveApiKey();
  if (key && !headers.has(NOVA_API_KEY_HEADER)) {
    headers.set(NOVA_API_KEY_HEADER, key);
  }
  return fetch(input, { ...init, headers });
}
