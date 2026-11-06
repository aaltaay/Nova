/**
 * @vitest-environment jsdom
 *
 * V4 end to end: the real App on ?view=sample, the gate installed the way
 * main.tsx installs it, and the network underneath it a spy. On load the desk
 * used to POST /api/bot/focus/sync (emptying the live bot's Trader list) and
 * read the live status, account and Sim session; its venue pills switched the
 * live desk. This fails if any of that reaches the network again.
 *
 * #449: the same for the operator's saved browser state, now that the sample
 * desk has its own Trader tabs, Focus rail and pop-out -- `setItem` /
 * `removeItem` underneath are spies too. The Market page (ADR 053) is walked
 * to as well, so it never writes or reaches the backend from the sample desk.
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import { GLOBAL_BAR_SEARCH_RECENTS_STORAGE_KEY } from '../constantGroups/global_bar';
import { LAYOUT_STORAGE_KEY, MODULE_VISIBILITY_STORAGE_KEY } from '../constantGroups/market_ui';
import { FOCUS_RAIL_STORAGE_KEY } from '../constantGroups/trader_chrome';
import { TRADE_DEFAULTS_STORAGE_KEY } from '../constantGroups/trade_defaults';
import {
  TRADER_BLOCK_NOTICE_STORAGE_KEY,
  TRADER_FLOAT_ID_READY_KEY,
  TRADER_LAST_HOST_KEY,
  TRADER_TABS_STORAGE_KEY,
  TRADER_WINDOW_ID_KEY,
} from '../constantGroups/trader_view';
import { WATCH_LIST_STORAGE_KEY } from '../watch_list/watchListConstants';
import { resetNavRailStoreForTests } from '../workspace/navRailStore';
import { TRADER_DOCK_CLAIM_KEY } from '../workspace/traderDesk/commands';
import { TRADER_DESK_STORAGE_KEY } from '../workspace/traderDesk/protocol';
import { SAMPLE_VENUE_REFUSAL } from './sampleCopy';
import { installSampleNetworkGate, uninstallSampleNetworkGateForTests } from './sampleNetworkGate';
import {
  installSampleStorageGate,
  SAMPLE_STORAGE_PASSTHROUGH,
  uninstallSampleStorageGateForTests,
} from './sampleStorageGate';

// jsdom has no canvas: the sample dashboard's price chart is not what this is about.
vi.mock('../chart/TickerChart', () => ({ TickerChart: () => null }));

const BACKEND = /^(?:https?|wss?):\/\/(?:127\.0\.0\.1|localhost):8000\/|^\/(?:api|ws|__nova)\//;

/*
 * #1129: sized from what a cold desk costs, not a quiet PC. With every core
 * busy, the first transform of the sample shell's lazy chunk alone outran the
 * 100 x 100 ms header wait and the 5 s test. The chunks are now warmed once,
 * and the waits run by the clock (a busy PC runs fewer settle steps a second).
 */
const WARM_CHUNKS_MS = 120_000;   // beforeAll: every lazy chunk the tests open, transformed once
const MOUNT_WAIT_MS = 20_000;     // a warmed chunk mounting
// Each test outlasts its own waits, so a page that never mounts fails on its assertion, not on the clock.
const DESK_TEST_MS = MOUNT_WAIT_MS + 10_000;           // the desk and its checks
const WORKSPACE_TEST_MS = 5 * MOUNT_WAIT_MS + 20_000;  // the desk, four pages, and the walk between them

beforeAll(async () => {
  await Promise.all([
    import('./SampleShell'),
    import('../market_board'),
    import('../global_board'),
    import('../forex_board'),
    import('../congress'),
  ]);
}, WARM_CHUNKS_MS);

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

/** Settles until `testId` is on screen or `MOUNT_WAIT_MS` has passed; the caller asserts it. */
async function waitForTestId(testId: string): Promise<void> {
  const until = Date.now() + MOUNT_WAIT_MS;
  while (!container.querySelector(`[data-testid="${testId}"]`) && Date.now() < until) {
    await settle(100);
  }
}

async function renderSampleDesk(): Promise<void> {
  await act(async () => {
    root.render(<App />);
  });
  // The sample shell is a lazy chunk; wait for it to mount.
  await waitForTestId('global-app-bar');
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
  }, DESK_TEST_MS);
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
  }, DESK_TEST_MS);
});

/*
 * #449: the sample desk's own workspace -- Trader tabs, the Focus rail and
 * pop-out -- then the Market page. Its doors keep the live workspace's keys untouched even
 * without the storage gate; with both gates installed as main.tsx installs
 * them, nothing at all reaches the browser's storage but the shell's one-shot
 * reload guard.
 */
const WORKSPACE_KEYS = [
  TRADER_TABS_STORAGE_KEY, TRADER_BLOCK_NOTICE_STORAGE_KEY, TRADER_WINDOW_ID_KEY, TRADER_FLOAT_ID_READY_KEY,
  TRADER_LAST_HOST_KEY, TRADER_DOCK_CLAIM_KEY, TRADER_DESK_STORAGE_KEY, FOCUS_RAIL_STORAGE_KEY,
  WATCH_LIST_STORAGE_KEY, LAYOUT_STORAGE_KEY, MODULE_VISIBILITY_STORAGE_KEY,
  GLOBAL_BAR_SEARCH_RECENTS_STORAGE_KEY, TRADE_DEFAULTS_STORAGE_KEY,
];

describe("the sample workspace writes none of the operator's saved state (#449)", () => {
  let stored: string[];
  let opened: string[];

  function q<T extends HTMLElement = HTMLElement>(testId: string): T {
    const el = container.querySelector<T>(`[data-testid="${testId}"]`);
    expect(el, `${testId} on screen; page reads: ${container.textContent?.slice(0, 200)}`).toBeTruthy();
    return el as T;
  }

  async function press(testId: string, event: 'click' | 'dblclick' = 'click'): Promise<void> {
    const el = q(testId);
    await act(async () => {
      el.dispatchEvent(new MouseEvent(event, { bubbles: true }));
    });
    await settle();
  }

  /** Tabs (open, preview, pin, switch), the Focus rail, pop-out, then the Market page. */
  async function workTheSampleWorkspace(): Promise<void> {
    await renderSampleDesk();
    q('focus-rail');
    await press('focus-rail-row-GAPX');
    q('sv-tab-GAPX');
    await press('sv-tab-pin-GAPX');
    await press('focus-rail-row-NWSR');
    const smplLabel = q('sv-tab-SMPL').querySelector<HTMLElement>('.sv-tab__label');
    await act(async () => { smplLabel?.click(); });
    expect(q('sv-tab-SMPL').getAttribute('aria-selected')).toBe('true');
    await press('sv-tab-extract-NWSR');
    expect(opened, 'the pop-out opened on the sample route').toHaveLength(1);
    expect(new URL(opened[0]).searchParams.get('view')).toBe('sample');
    expect(container.querySelector('[data-testid="sv-tab-NWSR"]'), 'popped out, so gone here').toBeNull();
    await press('nav-rail-market');
    // The page is a lazy chunk; wait for it to mount.
    await waitForTestId('market-page');
    q('market-page');
    expect(container.textContent).not.toMatch(/not available in Sample Data mode/);
    // The Global page (ADR 060) too: its sample board, and its switches never write the desk's storage.
    await press('nav-rail-global');
    await waitForTestId('global-page');
    q('global-page');
    await press('global-color-by-move');
    await press('global-period-7D');
    expect(container.textContent).toMatch(/Rotation, not an exit/);
    // The Forex page (ADR 062) too: its sample board, and its switches never write the desk's storage.
    await press('nav-rail-forex');
    await waitForTestId('forex-page');
    q('forex-page');
    await press('forex-color-by-futures');
    await press('forex-period-7D');
    expect(container.textContent).toMatch(/All forex/);
    // The Congress page (ADR 066) too: invented members, and its switches never write the desk's storage.
    await press('nav-rail-congress');
    await waitForTestId('congress-page');
    q('congress-page');
    await press('congress-seats-period-30d');
    await press('congress-topic-house');
    expect(container.textContent).toMatch(/Nova Marketing Sample Data/);
  }

  beforeEach(() => {
    stored = [];
    opened = [];
    const record = (key: string) => { stored.push(String(key)); };
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(record);
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(record);
    vi.spyOn(Storage.prototype, 'clear').mockImplementation(() => record('*'));
    vi.spyOn(window, 'open').mockImplementation((url) => {
      opened.push(String(url));
      return { focus: () => {}, opener: null } as unknown as Window;
    });
  });

  afterEach(() => {
    uninstallSampleStorageGateForTests();
    resetNavRailStoreForTests();
    vi.restoreAllMocks();
  });

  it('without the storage gate: tabs, Focus rail, pop-out and the Market page leave the workspace keys alone', async () => {
    mount('/?view=sample&symbol=SMPL', true);
    await workTheSampleWorkspace();
    expect(stored.filter((key) => WORKSPACE_KEYS.includes(key))).toEqual([]);
    expect(writesSent(), 'no write left the sample desk').toEqual([]);
  }, WORKSPACE_TEST_MS);

  it('with both gates: nothing reaches the browser storage but the reload guard', async () => {
    mount('/?view=sample&symbol=SMPL', true);
    // Installed over the spies, so the spies see only what passes the gate.
    installSampleStorageGate();
    await workTheSampleWorkspace();
    expect(stored.filter((key) => !SAMPLE_STORAGE_PASSTHROUGH.has(key))).toEqual([]);
    expect(writesSent(), 'no write left the sample desk').toEqual([]);
    expect(sent().filter((r) => BACKEND.test(r.url)), 'no backend read').toEqual([]);
    expect(backendSockets(), 'no backend socket').toEqual([]);
  }, WORKSPACE_TEST_MS);
});
