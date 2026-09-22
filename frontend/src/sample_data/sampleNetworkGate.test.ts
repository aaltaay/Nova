/**
 * @vitest-environment jsdom
 *
 * V4 (QA 2026-09-22): the sample desk sends nothing to Nova, reads none of its
 * live state and opens no backend socket. These fail if any sample-mode call
 * can reach the underlying fetch with a non-GET, read the backend, or open a
 * backend WebSocket -- and, the other direction, if the gate ever touches a
 * live-desk call.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { SAMPLE_NETWORK_REFUSAL } from './sampleCopy';
import {
  installSampleNetworkGate,
  isBackendUrl,
  SampleRefusedSocket,
  sampleNetworkRefusals,
  uninstallSampleNetworkGateForTests,
  type GateWindow,
} from './sampleNetworkGate';

const API = 'http://127.0.0.1:8000';
const PAGE = 'http://localhost:5173';

type SpySocketCtor = typeof WebSocket & { urls: string[] };

function spySocket(): SpySocketCtor {
  const urls: string[] = [];
  class NativeSocket extends EventTarget {
    static readonly CONNECTING = 0;
    static readonly OPEN = 1;
    static readonly CLOSING = 2;
    static readonly CLOSED = 3;
    readonly url: string;
    constructor(url: string | URL) {
      super();
      this.url = String(url);
      urls.push(this.url);
    }
  }
  return Object.assign(NativeSocket, { urls }) as unknown as SpySocketCtor;
}

function fakeWindow(path: string) {
  const native = vi.fn(async (..._args: Parameters<typeof fetch>) => new Response('{}', { status: 200 }));
  const beacon = vi.fn(() => true);
  const Socket = spySocket();
  const win: GateWindow = {
    location: { href: `${PAGE}${path}`, search: new URL(`${PAGE}${path}`).search },
    fetch: native as unknown as typeof fetch,
    WebSocket: Socket,
    navigator: { sendBeacon: beacon } as unknown as Navigator,
    __NOVA_API_BASE__: API,
  };
  installSampleNetworkGate(win);
  return { win, native, beacon, Socket };
}

afterEach(() => {
  uninstallSampleNetworkGateForTests();
});

const WRITES: Array<[string, string]> = [
  ['POST', `${API}/api/bot/focus/sync`],
  ['POST', `${API}/api/sim/history/select`],
  ['POST', `${API}/api/sim/replay`],
  ['POST', `${API}/api/sim/clock`],
  ['POST', `${API}/api/desk/venue`],
  ['POST', `${API}/api/bot/allowlist`],
  ['PATCH', `${API}/api/bot/session`],
  ['POST', `${API}/api/ibkr/order`],
  ['DELETE', `${API}/api/ibkr/order/1`],
  ['POST', `${PAGE}/__nova/start-api`],
  ['POST', `${API}/api/client-errors`],
  ['PUT', 'https://example.com/anything'],
];

describe('on the sample desk', () => {
  it.each(WRITES)('refuses %s %s without sending it', async (method, url) => {
    const { win, native } = fakeWindow('/?view=sample');
    const res = await win.fetch(url, { method, body: '{}' });
    expect(native).not.toHaveBeenCalled();
    expect(res.status).toBe(403);
    expect(await res.json()).toMatchObject({ detail: SAMPLE_NETWORK_REFUSAL, reason_code: 'SAMPLE_VIEW' });
  });

  it('refuses a write passed as a Request object', async () => {
    const { win, native } = fakeWindow('/?view=sample&symbol=GRML');
    await win.fetch(new Request(`${API}/api/sim/clock`, { method: 'POST', body: '{}' }));
    expect(native).not.toHaveBeenCalled();
  });

  it('reads none of the live backend', async () => {
    const { win, native } = fakeWindow('/?view=sample');
    for (const url of [
      `${API}/api/ibkr/status`,
      `${API}/api/practice/account?venue=paper`,
      `${API}/api/sim/clock`,
      `${API}/api/bot/session`,
      '/api/capture/sessions',
      '/__nova/api-status',
    ]) {
      const res = await win.fetch(url);
      expect(res.status, url).toBe(403);
    }
    expect(native).not.toHaveBeenCalled();
  });

  it('still loads its own static files', async () => {
    const { win, native } = fakeWindow('/?view=sample');
    await win.fetch('/assets/chunk.js');
    expect(native).toHaveBeenCalledTimes(1);
  });

  it('opens no backend socket, and the refused one reports itself closed', async () => {
    const { win, Socket } = fakeWindow('/?view=sample&symbol=GRML');
    const onclose = vi.fn();
    for (const url of ['ws://127.0.0.1:8000/ws/ibkr/depth/GRML', 'ws://127.0.0.1:8000/ws/ibkr/tape/GRML', 'ws://localhost:8000/ws/scanner']) {
      const ws = new win.WebSocket(url);
      expect(ws).toBeInstanceOf(SampleRefusedSocket);
      ws.onclose = onclose;
      ws.send('nothing');
    }
    expect(Socket.urls).toEqual([]);
    await new Promise((resolve) => setTimeout(resolve, 5));
    expect(onclose).toHaveBeenCalledTimes(3);
    expect(sampleNetworkRefusals().filter((r) => r.kind === 'websocket')).toHaveLength(3);
  });

  it('leaves the dev server hot-reload socket alone', () => {
    const { win, Socket } = fakeWindow('/?view=sample');
    new win.WebSocket(`ws://localhost:5173/?token=abc`);
    expect(Socket.urls).toEqual(['ws://localhost:5173/?token=abc']);
  });

  it('refuses beacons', () => {
    const { win, beacon } = fakeWindow('/?view=sample');
    expect(win.navigator?.sendBeacon(`${API}/api/client-errors`, '{}')).toBe(false);
    expect(beacon).not.toHaveBeenCalled();
  });
});

describe('everywhere else the gate is invisible', () => {
  it.each(['/', '/?view=stock&symbol=GRML', '/?view=samples', '/?view=SAMPLE'])(
    'passes every call through at %s',
    async (path) => {
      const { win, native, beacon, Socket } = fakeWindow(path);
      const init = { method: 'POST', body: '{"live":[]}' };
      await win.fetch(`${API}/api/bot/focus/sync`, init);
      expect(native).toHaveBeenCalledWith(`${API}/api/bot/focus/sync`, init);
      await win.fetch(`${API}/api/ibkr/status`);
      expect(native).toHaveBeenCalledTimes(2);
      const ws = new win.WebSocket('ws://127.0.0.1:8000/ws/ibkr/depth/GRML');
      expect(ws).not.toBeInstanceOf(SampleRefusedSocket);
      expect(Socket.urls).toEqual(['ws://127.0.0.1:8000/ws/ibkr/depth/GRML']);
      win.navigator?.sendBeacon(`${API}/api/client-errors`, '{}');
      expect(beacon).toHaveBeenCalledTimes(1);
    },
  );

  it('decides per call, so leaving the sample desk needs no reinstall', async () => {
    const { win, native } = fakeWindow('/?view=sample');
    await win.fetch(`${API}/api/desk/venue`, { method: 'POST' });
    expect(native).not.toHaveBeenCalled();
    win.location = { href: `${PAGE}/`, search: '' };
    await win.fetch(`${API}/api/desk/venue`, { method: 'POST' });
    expect(native).toHaveBeenCalledTimes(1);
  });
});

describe('isBackendUrl', () => {
  it('knows the API server under every loopback spelling and scheme', () => {
    for (const url of [`${API}/api/x`, 'ws://localhost:8000/ws/x', 'http://[::1]:8000/health', '/api/x', '/ws/ticker', '/__nova/start-api']) {
      expect(isBackendUrl(url, API, `${PAGE}/`), url).toBe(true);
    }
    for (const url of ['/assets/app.js', `${PAGE}/?token=1`, 'https://example.com/x']) {
      expect(isBackendUrl(url, API, `${PAGE}/`), url).toBe(false);
    }
  });
});

/*
 * The gate wraps the globals every module calls at call time. A module that
 * captured `fetch` / `WebSocket` into a variable at load, or used a transport
 * the gate does not wrap, would slip past it -- so the source tree may not.
 */
const SRC = join(dirname(fileURLToPath(import.meta.url)), '..');

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.(ts|tsx)$/.test(name) && !/\.test\.tsx?$/.test(name) ? [path] : [];
  });
}

describe('no transport outside the gate', () => {
  it('nothing captures fetch or WebSocket, or uses XMLHttpRequest / EventSource', () => {
    const offenders: string[] = [];
    const patterns = [
      /=\s*(?:window\.|globalThis\.)?fetch\s*(?:\.bind\b|;|$)/m,
      /=\s*(?:window\.|globalThis\.)?WebSocket\s*;/m,
      /new\s+XMLHttpRequest\b/,
      /new\s+EventSource\b/,
    ];
    for (const file of sourceFiles(SRC)) {
      if (file.endsWith(join('sample_data', 'sampleNetworkGate.ts'))) continue;
      // Test-only setup that walls tests off from the live backend; not app code.
      if (file.includes(join('src', 'testSetup'))) continue;
      const text = readFileSync(file, 'utf8');
      if (patterns.some((re) => re.test(text))) offenders.push(relative(SRC, file));
    }
    expect(offenders).toEqual([]);
  });

  it('main.tsx installs the gate before it loads the app', () => {
    const main = readFileSync(join(SRC, 'main.tsx'), 'utf8').replace(/\r\n/g, '\n');
    const gate = main.indexOf('installSampleNetworkGate(window)');
    const app = main.indexOf("import('./App.tsx')");
    expect(gate).toBeGreaterThan(-1);
    expect(app).toBeGreaterThan(gate);
  });
});
