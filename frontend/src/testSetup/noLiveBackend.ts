/**
 * Tests never reach the operator's live desk.
 *
 * Before this guard, a test that rendered a component with a real poller sent
 * `GET /api/ibkr/status` -- and anything else it called -- to 127.0.0.1:8000,
 * the operator's running backend, every time `vitest run` was started on this
 * machine (found by the QA orders batch, 2026-09-22). A test that mocks
 * `fetch` / `WebSocket` (vi.spyOn, vi.stubGlobal, a manual assignment) replaces
 * these wrappers and is unaffected. Anything that still reaches them for a Nova
 * backend URL gets a rejected fetch -- the same network error the app sees when
 * the API is down -- or an inert socket that closes on the next task.
 *
 * Wired via vite.config.ts `test.setupFiles`; not a product tunable.
 */
import { NOVA_DESKTOP_API_BASE } from '../constantGroups/chart_api';
import { isBackendUrl, SampleRefusedSocket } from '../sample_data/sampleNetworkGate';

export const LIVE_BACKEND_REFUSAL =
  'Tests never call the live Nova backend (src/testSetup/noLiveBackend.ts); mock fetch / WebSocket instead';

const FALLBACK_PAGE = 'http://localhost/';

function pageHref(): string {
  try {
    return globalThis.location?.href || FALLBACK_PAGE;
  } catch {
    return FALLBACK_PAGE;
  }
}

function urlOf(input: unknown): string {
  if (typeof input === 'string') return input;
  if (input instanceof URL) return input.href;
  if (input && typeof input === 'object' && 'url' in input) return String((input as { url: unknown }).url);
  return String(input);
}

function reachesBackend(url: string): boolean {
  return isBackendUrl(url, NOVA_DESKTOP_API_BASE, pageHref());
}

const nativeFetch = globalThis.fetch;
if (typeof nativeFetch === 'function') {
  globalThis.fetch = function noLiveBackendFetch(input: RequestInfo | URL, init?: RequestInit) {
    if (reachesBackend(urlOf(input))) return Promise.reject(new TypeError(LIVE_BACKEND_REFUSAL));
    return nativeFetch.call(globalThis, input, init);
  } as typeof fetch;
}

const NativeWebSocket = globalThis.WebSocket;
if (typeof NativeWebSocket === 'function') {
  globalThis.WebSocket = new Proxy(NativeWebSocket, {
    construct(target, args, newTarget) {
      const url = String(args[0]);
      if (reachesBackend(url)) return new SampleRefusedSocket(url) as unknown as WebSocket;
      return Reflect.construct(target, args, newTarget) as WebSocket;
    },
  });
}

export {};
