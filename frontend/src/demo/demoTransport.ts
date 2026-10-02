/**
 * The demo's transport (ADR 043): what makes it safe to run the desk on a public page. Installed
 * before any app module loads, it replaces `fetch`, `WebSocket` and `navigator.sendBeacon`:
 *
 *   - a request to the demo API origin, to a loopback host on any port, or to an `/api`, `/ws`,
 *     `/sensors` or `/__nova` path is answered in the page (demoApi.ts) and never sent -- a
 *     visitor's own Nova on 127.0.0.1 is never reached;
 *   - any other request that is not a GET or HEAD is refused in the page;
 *   - every WebSocket is a DemoSocket, connected to nothing.
 *
 * GETs for anything else (the page's own files) go to the network as usual.
 */
import { DEMO_REFUSAL, answer } from './demoApi';
import { DEMO_API_BASE } from './demoFlag';
import { DemoSocket } from './demoSockets';

const LOOPBACK = new Set(['localhost', '127.0.0.1', '[::1]', '::1']);
const BACKEND_PATH = /^\/(?:api|ws|sensors|__nova)(?:\/|$)/;
const DEMO_HOST = new URL(DEMO_API_BASE).host;
/** A breath of latency, so loading states look like a desk's and nothing answers re-entrantly. */
const LATENCY_MS = 25;
const MISSES_KEEP = 50;

export interface TransportWindow {
  location: Pick<Location, 'href'>;
  fetch: typeof fetch;
  WebSocket: typeof WebSocket;
  navigator?: Navigator;
}

/** Requests the demo had no answer for (404), newest last: what to add when a panel is blank. */
export const demoMisses: string[] = [];

/** True when `url` is the backend: the demo origin, a loopback host, or a backend path. A URL that does not parse counts. */
export function isDemoBackend(url: string, pageHref: string): boolean {
  let u: URL;
  try {
    u = new URL(url, pageHref);
  } catch {
    return true;
  }
  return u.host === DEMO_HOST || LOOPBACK.has(u.hostname.toLowerCase()) || BACKEND_PATH.test(u.pathname);
}

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

function parseBody(raw: unknown): unknown {
  if (typeof raw !== 'string') return null;
  try {
    return JSON.parse(raw);
  } catch {
    return raw;
  }
}

function urlOf(input: RequestInfo | URL): string {
  if (typeof input === 'string') return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

function aborted(): DOMException {
  return new DOMException('The operation was aborted.', 'AbortError');
}

/** Answer one backend request in the page. */
async function answerInPage(url: URL, method: string, body: unknown, signal?: AbortSignal | null): Promise<Response> {
  if (signal?.aborted) throw aborted();
  await new Promise((r) => setTimeout(r, LATENCY_MS));
  if (signal?.aborted) throw aborted();
  const res = answer({ method, path: url.pathname, query: url.searchParams, body });
  if (res) return json(res.status, res.body);
  demoMisses.push(`${method} ${url.pathname}`);
  if (demoMisses.length > MISSES_KEEP) demoMisses.splice(0, demoMisses.length - MISSES_KEEP);
  return json(404, { detail: 'Not part of the demo.' });
}

let installedOn: TransportWindow | null = null;

/** Replace `fetch`, `WebSocket` and `sendBeacon` on `win` once. */
export function installDemoTransport(win: TransportWindow): void {
  if (installedOn === win) return;
  const nativeFetch = win.fetch.bind(win);

  win.fetch = async function demoFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
    const request = input instanceof Request ? input : null;
    const method = String(init?.method ?? request?.method ?? 'GET').toUpperCase();
    const raw = urlOf(input);
    if (isDemoBackend(raw, win.location.href)) {
      const text = init?.body ?? (request && method !== 'GET' && method !== 'HEAD' ? await request.clone().text() : null);
      return answerInPage(new URL(raw, win.location.href), method, parseBody(text), init?.signal ?? request?.signal);
    }
    if (method !== 'GET' && method !== 'HEAD') return json(403, { detail: DEMO_REFUSAL, reason: 'DEMO' });
    return nativeFetch(input, init);
  } as typeof fetch;

  win.WebSocket = DemoSocket as unknown as typeof WebSocket;

  const nav = win.navigator;
  if (nav && typeof nav.sendBeacon === 'function') {
    // A beacon is a POST: the desk's own reports are taken in the page; anything else is refused.
    nav.sendBeacon = (url: string | URL): boolean => {
      const href = String(url);
      if (!isDemoBackend(href, win.location.href)) return false;
      answer({ method: 'POST', path: new URL(href, win.location.href).pathname, query: new URLSearchParams(), body: null });
      return true;
    };
  }
  installedOn = win;
}
