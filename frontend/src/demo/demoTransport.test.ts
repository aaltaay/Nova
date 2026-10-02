/**
 * @vitest-environment jsdom
 *
 * The demo's transport (ADR 043) is what makes a public page safe: nothing aimed at a backend -- the
 * demo origin, a loopback host on any port, an /api or /ws path -- may reach the real network, and
 * nothing that is not a read may leave at all.
 */
import { describe, expect, it, vi } from 'vitest';
import { DEMO_REFUSAL } from './demoApi';
import { DEMO_API_BASE } from './demoFlag';
import { DemoSocket } from './demoSockets';
import { installDemoTransport, isDemoBackend, type TransportWindow } from './demoTransport';

const PAGE = 'https://nova.altaystudio.com/demo/';

function fakeWindow() {
  const native = vi.fn(async () => new Response('static file', { status: 200 }));
  const beacon = vi.fn(() => true);
  const win = {
    location: { href: PAGE },
    fetch: native as unknown as typeof fetch,
    WebSocket: class {} as unknown as typeof WebSocket,
    navigator: { sendBeacon: beacon } as unknown as Navigator,
  } satisfies TransportWindow;
  installDemoTransport(win);
  return { win, native, beacon };
}

describe('isDemoBackend', () => {
  it('counts the demo origin, every loopback host and every backend path', () => {
    for (const url of [
      `${DEMO_API_BASE}/api/health`, 'http://127.0.0.1:8000/api/ibkr/order', 'http://localhost:5173/x',
      'http://[::1]:9000/', '/api/gappers', '/ws/hod-momo', '/sensors/focus', 'https://elsewhere.example/api/x',
    ]) expect(isDemoBackend(url, PAGE)).toBe(true);
    for (const url of ['/demo/assets/main.js', 'https://fonts.googleapis.com/css2?family=Geist']) {
      expect(isDemoBackend(url, PAGE)).toBe(false);
    }
  });
});

describe('installDemoTransport', () => {
  it("answers a visitor's local Nova in the page, never on the network", async () => {
    const { win, native } = fakeWindow();
    const res = await win.fetch('http://127.0.0.1:8000/api/health');
    expect(res.status).toBe(200);
    expect(((await res.json()) as { status: string }).status).toBe('connected');
    const order = await win.fetch(`${DEMO_API_BASE}/api/ibkr/order`, { method: 'POST', body: JSON.stringify({ symbol: 'SMPL', qty: 100 }) });
    expect(order.status).toBe(403);
    expect(((await order.json()) as { detail: string }).detail).toBe(DEMO_REFUSAL);
    expect(native).not.toHaveBeenCalled();
  });

  it('refuses any write to anywhere else, and lets reads of the page through', async () => {
    const { win, native } = fakeWindow();
    expect((await win.fetch('https://elsewhere.example/collect', { method: 'POST', body: 'x' })).status).toBe(403);
    expect(native).not.toHaveBeenCalled();
    await win.fetch('/demo/icons.svg');
    expect(native).toHaveBeenCalledTimes(1);
  });

  it('honours an aborted request', async () => {
    const { win } = fakeWindow();
    const ctl = new AbortController();
    ctl.abort();
    await expect(win.fetch('/api/health', { signal: ctl.signal })).rejects.toMatchObject({ name: 'AbortError' });
  });

  it('makes every socket a page-local one, and keeps beacons in the page', () => {
    const { win, beacon } = fakeWindow();
    expect(win.WebSocket).toBe(DemoSocket);
    expect(win.navigator.sendBeacon('http://127.0.0.1:8000/api/perf/client', '{}')).toBe(true);
    expect(win.navigator.sendBeacon('https://elsewhere.example/beacon', '{}')).toBe(false);
    expect(beacon).not.toHaveBeenCalled();
  });
});
