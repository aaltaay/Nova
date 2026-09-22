/**
 * @vitest-environment jsdom
 *
 * V4 end to end: the real App on ?view=sample, the gate installed the way
 * main.tsx installs it, and the network underneath it a spy. On load the desk
 * used to POST /api/bot/focus/sync (emptying the live bot's Trader list) and
 * read the live status, account and Sim session; its venue pills switched the
 * live desk. This fails if any of that reaches the network again.
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import { SAMPLE_VENUE_REFUSAL } from './sampleCopy';
import { installSampleNetworkGate, uninstallSampleNetworkGateForTests } from './sampleNetworkGate';

// jsdom has no canvas: the sample dashboard's price chart is not what this is about.
vi.mock('../chart/TickerChart', () => ({ TickerChart: () => null }));

const BACKEND = /^(?:https?|wss?):\/\/(?:127\.0\.0\.1|localhost):8000\/|^\/(?:api|ws|__nova)\//;

let root: Root;
let container: HTMLDivElement;
let native: ReturnType<typeof vi.fn>;
let socketUrls: string[];
let savedFetch: typeof fetch;
let savedSocket: typeof WebSocket;

function spySocket(): typeof WebSocket {
  class Socket extends EventTarget {
    static readonly CONNECTING = 0;
    static readonly OPEN = 1;
    static readonly CLOSING = 2;
    static readonly CLOSED = 3;
    readyState = 0;
    constructor(url: string | URL) {
      super();
      socketUrls.push(String(url));
    }
    send(): void {}
    close(): void {}
  }
  return Socket as unknown as typeof WebSocket;
}

async function settle(ms = 30): Promise<void> {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, ms));
  });
}

function sent(): Array<{ method: string; url: string }> {
  return native.mock.calls.map(([input, init]) => ({
    method: String((init as RequestInit | undefined)?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase(),
    url: typeof input === 'string' ? input : input instanceof URL ? input.href : (input as Request).url,
  }));
}

function mount(path: string, gate: boolean): void {
  window.history.replaceState({}, '', path);
  savedFetch = window.fetch;
  savedSocket = window.WebSocket;
  native = vi.fn(async () => new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } }));
  socketUrls = [];
  window.fetch = native as unknown as typeof fetch;
  window.WebSocket = spySocket();
  if (gate) installSampleNetworkGate(window);
  Element.prototype.scrollTo = vi.fn();
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
}

async function renderSampleDesk(): Promise<void> {
  await act(async () => {
    root.render(<App />);
  });
  // The sample shell is a lazy chunk; wait for it to mount.
  for (let i = 0; i < 100 && !container.querySelector('[data-testid="global-app-bar"]'); i += 1) {
    await settle(100);
  }
  await settle(200);
  expect(
    container.querySelector('[data-testid="global-app-bar"]'),
    `sample header mounted; page reads: ${container.textContent?.slice(0, 300)}`,
  ).toBeTruthy();
}

const writesSent = () => sent().filter((r) => r.method !== 'GET' && r.method !== 'HEAD');
const backendSockets = () => socketUrls.filter((u) => BACKEND.test(u));

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  uninstallSampleNetworkGateForTests();
  window.fetch = savedFetch;
  window.WebSocket = savedSocket;
  window.history.replaceState({}, '', '/');
});

/*
 * Without the gate: the desk's own doors must already keep quiet -- no bot
 * focus sync on load, no live depth or tape line on the sample Trader. The
 * gate is the backstop, not the only wall.
 */
describe('the sample desk sends nothing of its own accord', () => {
  it.each(['/?view=sample', '/?view=sample&symbol=GRML'])('%s: no write, no backend socket', async (path) => {
    mount(path, false);
    await renderSampleDesk();
    expect(writesSent(), 'no write from the sample desk').toEqual([]);
    expect(backendSockets(), 'no live depth / tape / scanner line').toEqual([]);
  });
});

describe('the sample desk reaches no backend', () => {
  beforeEach(() => {
    mount('/?view=sample', true);
  });

  it('sends nothing on load, and its venue pill switches nothing', async () => {
    await renderSampleDesk();

    const live = container.querySelector<HTMLButtonElement>('[data-testid="header-gateway-mode-capsule-live"]');
    expect(live, 'venue pill rendered').toBeTruthy();
    await act(async () => {
      live?.click();
    });
    await settle();
    expect(container.textContent).toContain(SAMPLE_VENUE_REFUSAL);

    const reads = sent().filter((r) => BACKEND.test(r.url));
    expect(writesSent(), 'no write left the sample desk').toEqual([]);
    expect(reads, 'no backend read left the sample desk').toEqual([]);
    expect(backendSockets(), 'no backend socket').toEqual([]);
  });
});
