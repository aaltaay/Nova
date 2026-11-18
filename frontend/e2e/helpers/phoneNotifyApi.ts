/**
 * The stand-in for what the phone's Search, HOD Momo list and Notifications read (ADR 070, amendment
 * 2026-11-18): the notification settings behind the PIN's session, the listed-symbol directory, and the
 * HOD Momo feed. Called by `mockPhoneApi`, so every phone spec has it. All of it is Nova Marketing Sample Data.
 *
 * It also stands in for the phone itself where a test browser has no push service: `fakePush` gives the page
 * Android's answer to "allow notifications?" and a push address, and records what the page asked of them.
 */
import type { Page } from '@playwright/test';

const API = 'http://127.0.0.1:8000';

export interface NotifyStandIn {
  settings: Record<string, unknown>;
  publicKey: string | null;
  deviceIds: string[];
  lastSent: { at: number; title: string; ok: boolean; error: string | null } | null;
  /** The bodies of every settings write, in order. */
  saved: Record<string, unknown>[];
}

export const NOTIFY_DEFAULTS = {
  schema_version: 1, hod_momo: 'off', setups: false, new_leader: false, fills: false, loss_limit: false,
  days: [0, 1, 2, 3, 4], start: '07:00', end: '16:00',
};

/** A P-256 public point, base64url: what a real PC's key looks like to the page (sample bytes, not a key in use). */
const SAMPLE_PUBLIC_KEY = 'BP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A8';
export const SAMPLE_ENDPOINT = 'https://fcm.googleapis.com/fcm/send/sample-phone';

/** Sample listings beyond the scanner's own tickers: `[symbol, name, exchange]`. */
const DIRECTORY: readonly [string, string, string][] = [
  ['ABCD', 'Sample Alpha Holdings Inc. Class A Ordinary Shares', 'NASDAQ'],
  ['ABCE', 'Sample Abacus Energy Corp. Common Stock', 'NYSE'],
  ['ABDX', 'Sample Abdex Therapeutics Inc. Common Stock', 'NASDAQ'],
  ['ABEL', 'Sample Abel Robotics Ltd. American Depositary Shares', 'NASDAQ'],
  ['ABFT', 'Sample Abaft Marine Inc.', 'AMEX'],
  ['ABGX', 'Sample Abigail Genomics Inc. Common Stock', 'NASDAQ'],
  ['ABHL', 'Sample Abhill Logistics Corp.', 'NYSE'],
  ['ABIO', 'Sample Abio Sciences Inc. Common Stock', 'NASDAQ'],
  ['ABJT', 'Sample Abject Tooling Ltd.', 'AMEX'],
  ['ABKR', 'Sample Abaker Foods Inc. Common Stock', 'NYSE'],
  ['WXYZ', 'Sample Wexley Zinc Corp. Common Stock', 'NASDAQ'],
  ['QRST', 'Sample Quarrystone Ltd.', 'NYSE'],
  ['ZEBR', 'Sample Zebra Aerospace Inc. Common Stock', 'NASDAQ'],
];

function alert(ticker: string, strategyId: number, name: string, agoSec: number, i: number) {
  const ts = Date.now() / 1000 - agoSec;
  return {
    id: `${Math.round(ts * 1000)}-${ticker}-${strategyId}`, timestamp: new Date(ts * 1000).toISOString(), ticker,
    strategy_id: strategyId, strategy_name: name, price: 1.44 + i * 0.83, change_pct: 16.3 + i * 9.1, rvol: 47 + i * 23,
    rvol_5min: null, float_shares: 2_940_000 + i * 410_000, gap_pct: null, volume: 6_320_000 - i * 380_000,
    momentum_pct: null, rvol_source: 'ibkr_pace', consolidation_count: 1, consolidated_ids: [],
    consolidation_span_sec: null, created_ts: ts,
  };
}

/** Today's alerts, newest first: 14 stocks on HOD Momo (more than a page), 2 on Running Up. */
function hodAlerts() {
  const stocks = ['ABCD', 'WXYZ', 'QRST', 'LMNO', 'EFGH', 'IJKL', 'UVWX', 'MNOP', 'CDEF', 'GHIJ', 'KLMN', 'OPQR', 'STUV', 'YZAB'];
  const out = [
    alert('ABCD', 12, 'Running Up Alert', 20, 0),
    alert('ZEBR', 12, 'Running Up Alert', 45, 1),
    // ABCD alerted again a minute ago: one row, two alerts, its first catch's place.
    alert('ABCD', 10, 'Squeeze Alert - Up 10% in 10min', 60, 0),
  ];
  stocks.forEach((ticker, i) => out.push(alert(ticker, i % 3 === 2 ? 13 : 11, i % 3 === 2 ? 'Approaching HOD' : 'Squeeze Alert - Up 5% in 5min', 90 + i * 420, i)));
  return out;
}

export async function mockPhoneNotify(
  page: Page,
  door: { unlocked: (token: string | null) => boolean; wrote: (line: string) => void },
): Promise<NotifyStandIn> {
  const notify: NotifyStandIn = { settings: { ...NOTIFY_DEFAULTS }, publicKey: null, deviceIds: [], lastSent: null, saved: [] };
  const view = () => ({
    schema_version: 1, available: true, why_unavailable: null, public_key: notify.publicKey, settings: notify.settings,
    device_ids: notify.deviceIds, last_sent: notify.lastSent,
  });

  await page.route(`${API}/api/symbols/directory`, (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ schema_version: 1, source: 'alpaca_assets', fetched_at: Date.now() / 1000, count: DIRECTORY.length, error: null, symbols: DIRECTORY }),
  }));

  await page.route(`${API}/api/phone/notify**`, async (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    const json = (body: unknown, code = 200) => route.fulfill({ status: code, contentType: 'application/json', body: JSON.stringify(body) });
    if (req.method() === 'GET') return json(view());
    door.wrote(`${req.method()} ${path}`);
    if (!door.unlocked(req.headers()['x-nova-phone-session'] ?? null)) {
      return json({ detail: { reason: 'PHONE_LOCKED', error: 'Unlock with your PIN first. Nothing was sent.' } }, 401);
    }
    const body = (req.postDataJSON() ?? {}) as Record<string, unknown>;
    switch (path.slice('/api/phone/notify/'.length)) {
      case 'key':
        notify.publicKey = notify.publicKey ?? SAMPLE_PUBLIC_KEY;
        return json(view());
      case 'settings':
        notify.saved.push(body);
        notify.settings = body;
        return json(view());
      case 'subscribe': {
        const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(String(body.endpoint)));
        const id = [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('').slice(0, 16);
        notify.deviceIds = [...notify.deviceIds.filter((d) => d !== id), id];
        return json(view());
      }
      case 'unsubscribe':
        notify.deviceIds = [];
        return json(view());
      case 'test':
        if (!notify.deviceIds.length) return json({ detail: { reason: 'PHONE_NOTIFY_NO_DEVICE', error: 'No phone is subscribed. Turn Notify this phone on first.' } }, 409);
        notify.lastSent = { at: Date.now() / 1000, title: 'Nova can reach this phone', ok: true, error: null };
        return json({ ...view(), text: 'Sent to 1 phone. It should arrive in a few seconds.' });
      default:
        return json({ detail: 'Not Found' }, 404);
    }
  });

  // The HOD Momo feed: today's whole list on connect, then quiet.
  await page.routeWebSocket(/127\.0\.0\.1:8000\/ws\/hod-momo/, (socket) => {
    const alerts = hodAlerts();
    socket.send(JSON.stringify({ type: 'initial', alerts, total: alerts.length }));
  });
  return notify;
}

/**
 * Stand in for the phone's own half of a push: Android's permission answer and the browser's push address.
 * `permission`: what the phone answers when asked ("default" until then, unless it starts at `granted` or
 * `denied`). The page's calls are counted on `window.__push`.
 */
export async function fakePush(page: Page, permission: 'granted' | 'denied', start: 'default' | 'granted' | 'denied' = 'default'): Promise<void> {
  await page.addInitScript(([answer, initial, endpoint]) => {
    const calls = { asked: 0, registered: [] as string[], subscribed: 0, unsubscribed: 0 };
    let now = initial;
    let sub: unknown = null;
    const bytes = (n: number) => new Uint8Array(n).fill(7).buffer;
    const b64 = (n: number) => btoa(String.fromCharCode(...new Uint8Array(bytes(n)))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
    const makeSub = (key: ArrayBuffer | null) => ({
      endpoint,
      options: { applicationServerKey: key, userVisibleOnly: true },
      toJSON: () => ({ endpoint, keys: { p256dh: b64(65), auth: b64(16) } }),
      unsubscribe: async () => { calls.unsubscribed += 1; sub = null; return true; },
    });
    const registration = {
      active: {},
      installing: null,
      waiting: null,
      pushManager: {
        getSubscription: async () => sub,
        subscribe: async (opts: { applicationServerKey: Uint8Array }) => {
          calls.subscribed += 1;
          sub = makeSub(opts.applicationServerKey.buffer as ArrayBuffer);
          return sub;
        },
      },
    };
    let registered = false;
    const worker = {
      // As on the real page: this worker's scope does not hold /phone.html, so `ready` never resolves.
      ready: new Promise(() => undefined),
      getRegistration: async () => (registered ? registration : undefined),
      register: async (url: string) => { calls.registered.push(url); registered = true; return registration; },
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    };
    Object.defineProperty(navigator, 'serviceWorker', { configurable: true, value: worker });
    class FakeNotification {
      static get permission() { return now; }
      static async requestPermission() { calls.asked += 1; now = answer; return now; }
    }
    Object.defineProperty(window, 'Notification', { configurable: true, value: FakeNotification });
    if (!('PushManager' in window)) Object.defineProperty(window, 'PushManager', { configurable: true, value: class {} });
    (window as unknown as { __push: typeof calls }).__push = calls;
  }, [permission, start, SAMPLE_ENDPOINT] as const);
}
