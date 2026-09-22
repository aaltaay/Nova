/**
 * Transport gate for the sample desk (V4, QA 2026-09-22; follows #357).
 *
 * The order doors refuse with their own copy (sampleOrderGuard), but the QA
 * sweep found the sample desk still writing to the live backend from other
 * places -- the bot focus sync on every load, Sim replay close / clock /
 * select, the venue switch, the row Allowlist -- and opening live depth and
 * tape sockets, while its header and pages showed the live account. Guarding
 * each caller cannot be proven complete, so this module is the backstop under
 * all of them: one wrapper around `fetch`, `WebSocket` and
 * `navigator.sendBeacon`, installed once in main.tsx before any app module
 * loads, that on the sample route
 *
 *   - refuses every non-GET request, to any URL, with a local 403 whose
 *     `detail` is SAMPLE_NETWORK_REFUSAL -- nothing is sent;
 *   - refuses every read of the Nova backend (its API origin, or any
 *     `/api/`, `/ws/`, `/__nova/` path) the same way, so no live state can
 *     reach a sample surface;
 *   - hands back an inert socket for every backend WebSocket: it never
 *     connects and reports itself closed.
 *
 * Off the sample route every call passes straight through. The decision is
 * made per call from the URL (sampleNav.isSampleView), like the order guard,
 * so entering or leaving the sample desk needs no re-install, and only an
 * exact `view=sample` match can refuse anything. XMLHttpRequest and
 * EventSource are not wrapped because Nova does not use them;
 * sampleNetworkGate.test.ts fails if a module starts to.
 */
import { NOVA_DESKTOP_API_BASE } from '../constantGroups/chart_api';
import { SAMPLE_NETWORK_REFUSAL, SAMPLE_VIEW_REASON_CODE } from './sampleCopy';
import { isSampleView } from './sampleNav';

/** Paths the Vite proxy or the API itself serves: always the backend. */
const BACKEND_PATH = /^\/(?:api|ws|__nova)(?:\/|$)/;
const LOOPBACK_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]', '::1']);
const SAFE_METHODS = new Set(['GET', 'HEAD']);
/** Refusals remembered for diagnostics and tests; older entries fall off. */
const REFUSAL_LOG_MAX = 50;
/** WebSocket close code for a policy refusal (RFC 6455 section 7.4.1). */
const POLICY_VIOLATION_CLOSE = 1008;
const HTTP_FORBIDDEN = 403;

export type SampleRefusalKind = 'fetch' | 'websocket' | 'beacon';

export interface SampleRefusal {
  kind: SampleRefusalKind;
  method: string;
  url: string;
  ts: number;
}

/** The window members the gate wraps and reads; a test passes a stand-in. */
export interface GateWindow {
  location: Pick<Location, 'href' | 'search'>;
  fetch: typeof fetch;
  WebSocket: typeof WebSocket;
  navigator?: Navigator;
  novaDesktop?: { apiBase?: string };
  __NOVA_API_BASE__?: string;
}

interface Installed {
  win: GateWindow;
  fetch: typeof fetch;
  WebSocket: typeof WebSocket;
  sendBeacon: Navigator['sendBeacon'] | null;
}

let installed: Installed | null = null;
const refusals: SampleRefusal[] = [];

function remember(kind: SampleRefusalKind, method: string, url: string): void {
  refusals.push({ kind, method, url, ts: Date.now() });
  if (refusals.length > REFUSAL_LOG_MAX) refusals.splice(0, refusals.length - REFUSAL_LOG_MAX);
}

/** What the gate refused since load (newest last). */
export function sampleNetworkRefusals(): readonly SampleRefusal[] {
  return refusals;
}

function parse(url: string, base: string): URL | null {
  try {
    return new URL(url, base);
  } catch {
    return null;
  }
}

function portOf(u: URL): string {
  if (u.port) return u.port;
  return u.protocol === 'https:' || u.protocol === 'wss:' ? '443' : '80';
}

/** Same host and port, treating every loopback spelling as one host (ws:// vs http:// ignored). */
function sameServer(a: URL, b: URL): boolean {
  if (portOf(a) !== portOf(b)) return false;
  const ha = a.hostname.toLowerCase();
  const hb = b.hostname.toLowerCase();
  return ha === hb || (LOOPBACK_HOSTS.has(ha) && LOOPBACK_HOSTS.has(hb));
}

function apiBaseOf(win: GateWindow): string {
  return (
    win.novaDesktop?.apiBase?.trim()
    || win.__NOVA_API_BASE__?.trim()
    || NOVA_DESKTOP_API_BASE
  );
}

/**
 * True when `url` reaches the Nova backend: an `/api/`, `/ws/` or `/__nova/`
 * path on any origin, or anything on the API server itself. A URL that does
 * not parse counts as the backend, so the sample desk fails closed.
 */
export function isBackendUrl(url: string, apiBase: string, pageHref: string): boolean {
  const target = parse(url, pageHref);
  if (!target) return true;
  if (BACKEND_PATH.test(target.pathname)) return true;
  const api = parse(apiBase, pageHref);
  return api != null && sameServer(target, api);
}

function onSampleRoute(win: GateWindow): boolean {
  return isSampleView(win.location?.search ?? '');
}

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === 'string') return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  const raw = init?.method ?? (typeof input === 'object' && 'method' in input ? input.method : 'GET');
  return String(raw || 'GET').toUpperCase();
}

/** Why the gate refuses this request on `win`, or null to let it through. */
export function sampleFetchRefusal(
  win: GateWindow,
  input: RequestInfo | URL,
  init?: RequestInit,
): string | null {
  if (!onSampleRoute(win)) return null;
  const method = requestMethod(input, init);
  if (!SAFE_METHODS.has(method)) return SAMPLE_NETWORK_REFUSAL;
  return isBackendUrl(requestUrl(input), apiBaseOf(win), win.location.href)
    ? SAMPLE_NETWORK_REFUSAL
    : null;
}

function refusalResponse(detail: string): Response {
  return new Response(JSON.stringify({ detail, reason_code: SAMPLE_VIEW_REASON_CODE }), {
    status: HTTP_FORBIDDEN,
    headers: { 'Content-Type': 'application/json' },
  });
}

type SocketHandler = ((this: WebSocket, ev: Event) => unknown) | null;

/**
 * What a refused backend WebSocket is: it never connects, sends nothing, and
 * reports `error` then `close` (1008) on the next task so reconnect loops see
 * an ordinary closed socket and back off.
 */
export class SampleRefusedSocket extends EventTarget {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;
  readonly CONNECTING = 0;
  readonly OPEN = 1;
  readonly CLOSING = 2;
  readonly CLOSED = 3;
  readonly url: string;
  readonly protocol = '';
  readonly extensions = '';
  readonly bufferedAmount = 0;
  binaryType: BinaryType = 'blob';
  readyState = 0;
  onopen: SocketHandler = null;
  onmessage: SocketHandler = null;
  onerror: SocketHandler = null;
  onclose: SocketHandler = null;

  constructor(url: string | URL) {
    super();
    this.url = String(url);
    setTimeout(() => this.refuse(), 0);
  }

  /** Inert: the sample desk never sends a frame. */
  send(): void {}

  close(): void {
    this.readyState = SampleRefusedSocket.CLOSED;
  }

  private fire(type: 'error' | 'close', event: Event): void {
    const handler = type === 'error' ? this.onerror : this.onclose;
    handler?.call(this as unknown as WebSocket, event);
    this.dispatchEvent(event);
  }

  private refuse(): void {
    if (this.readyState === SampleRefusedSocket.CLOSED) return;
    this.readyState = SampleRefusedSocket.CLOSED;
    this.fire('error', new Event('error'));
    const close =
      typeof CloseEvent === 'function'
        ? new CloseEvent('close', { code: POLICY_VIOLATION_CLOSE, reason: SAMPLE_NETWORK_REFUSAL, wasClean: false })
        : new Event('close');
    this.fire('close', close);
  }
}

function socketRefused(win: GateWindow, url: string): boolean {
  return onSampleRoute(win) && isBackendUrl(url, apiBaseOf(win), win.location.href);
}

/**
 * Wrap `win.fetch`, `win.WebSocket` and `win.navigator.sendBeacon` once.
 * Safe to call again (no second wrapper); off the sample route the wrappers
 * hand every call to the originals unchanged.
 */
export function installSampleNetworkGate(win: GateWindow = window): void {
  if (installed?.win === win) return;
  const nativeFetch = win.fetch;
  const NativeWebSocket = win.WebSocket;
  const nav = win.navigator;
  const nativeBeacon = nav && typeof nav.sendBeacon === 'function' ? nav.sendBeacon : null;

  win.fetch = function sampleGatedFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
    const refusal = sampleFetchRefusal(win, input, init);
    if (refusal) {
      remember('fetch', requestMethod(input, init), requestUrl(input));
      return Promise.resolve(refusalResponse(refusal));
    }
    return nativeFetch.call(win, input, init);
  } as typeof fetch;

  if (typeof NativeWebSocket === 'function') {
    win.WebSocket = new Proxy(NativeWebSocket, {
      construct(target, args, newTarget) {
        const url = String(args[0]);
        if (socketRefused(win, url)) {
          remember('websocket', 'GET', url);
          return new SampleRefusedSocket(url);
        }
        return Reflect.construct(target, args, newTarget) as WebSocket;
      },
    });
  }

  if (nav && nativeBeacon) {
    nav.sendBeacon = function sampleGatedBeacon(url: string | URL, data?: BodyInit | null): boolean {
      if (onSampleRoute(win)) {
        remember('beacon', 'POST', String(url));
        return false;
      }
      return nativeBeacon.call(nav, url, data);
    };
  }

  installed = { win, fetch: nativeFetch, WebSocket: NativeWebSocket, sendBeacon: nativeBeacon };
}

/** Test helper: put the originals back and forget the refusals. */
export function uninstallSampleNetworkGateForTests(): void {
  if (!installed) return;
  const { win, fetch: nativeFetch, WebSocket: NativeWebSocket, sendBeacon } = installed;
  win.fetch = nativeFetch;
  win.WebSocket = NativeWebSocket;
  if (win.navigator && sendBeacon) win.navigator.sendBeacon = sendBeacon;
  installed = null;
  refusals.length = 0;
}
