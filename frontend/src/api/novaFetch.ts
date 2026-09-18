/**
 * fetch wrapper that attaches X-Nova-Api-Key when a desktop, Vite, or
 * localStorage key is present. POST /api/config always requires this header
 * (D-040), even on loopback.
 */
import { NOVA_API_KEY_HEADER, NOVA_API_KEY_STORAGE } from '../constantGroups/api_auth';

export function resolveNovaApiKey(): string {
  const fromDesktop = typeof window !== 'undefined'
    ? window.novaDesktop?.apiKey?.trim()
    : '';
  if (fromDesktop) return fromDesktop;
  const fromEnv = (import.meta.env.VITE_NOVA_API_KEY as string | undefined)?.trim();
  if (fromEnv) return fromEnv;
  if (typeof localStorage !== 'undefined') {
    const fromStorage = localStorage.getItem(NOVA_API_KEY_STORAGE)?.trim();
    if (fromStorage) return fromStorage;
  }
  return '';
}

export function hasNovaApiKey(): boolean {
  return Boolean(resolveNovaApiKey());
}

export function writeNovaApiKey(value: string): void {
  if (typeof localStorage === 'undefined') return;
  const trimmed = value.trim();
  if (trimmed) localStorage.setItem(NOVA_API_KEY_STORAGE, trimmed);
  else localStorage.removeItem(NOVA_API_KEY_STORAGE);
}

export function novaFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const key = resolveNovaApiKey();
  if (key && !headers.has(NOVA_API_KEY_HEADER)) {
    headers.set(NOVA_API_KEY_HEADER, key);
  }
  return fetch(input, { ...init, headers });
}
