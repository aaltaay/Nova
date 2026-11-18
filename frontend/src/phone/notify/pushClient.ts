/**
 * This phone's half of a notification (ADR 070 amendment 2026-11-18): Chrome's own push.
 *
 * The page registers a small service worker (`/phone/sw.js`) and asks the browser for a push address: an
 * address at the browser maker's push service, with the two keys a sender needs to scramble a message so
 * only this phone can read it. The page hands that address to the PC; from then on the PC sends, and the
 * worker shows what arrives, with the page closed and the phone locked.
 *
 * Nothing here decides what is sent. The worker's scope is `/phone/`, so it never controls a page: it only
 * receives pushes and answers a tap.
 */

export const PUSH_WORKER_URL = '/phone/sw.js';
const PUSH_WORKER_SCOPE = '/phone/';

/** The push address and keys, as the PC stores them. */
export interface PushAddress {
  endpoint: string;
  keys: { p256dh: string; auth: string };
}

/** Whether this browser can receive a push at all; the reason when it cannot. */
export function pushSupport(): string | null {
  if (typeof window === 'undefined') return 'No browser.';
  if (!window.isSecureContext) return 'Notifications need the https address of your PC (the tunnel).';
  if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) {
    return 'This browser cannot receive notifications. Open Nova in Chrome on the phone.';
  }
  return null;
}

/** Android's answer for Nova: asked and allowed, asked and blocked, or not asked yet. */
export function pushPermission(): NotificationPermission | 'unsupported' {
  return pushSupport() ? 'unsupported' : Notification.permission;
}

/** The PC's public key as the browser wants it. */
export function keyBytes(base64url: string): Uint8Array<ArrayBuffer> {
  const padded = base64url.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(base64url.length / 4) * 4, '=');
  const raw = atob(padded);
  const out = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i += 1) out[i] = raw.charCodeAt(i);
  return out;
}

function addressOf(sub: PushSubscription): PushAddress | null {
  const json = sub.toJSON();
  const p256dh = json.keys?.p256dh;
  const auth = json.keys?.auth;
  return json.endpoint && p256dh && auth ? { endpoint: json.endpoint, keys: { p256dh, auth } } : null;
}

async function registration(): Promise<ServiceWorkerRegistration> {
  const existing = await navigator.serviceWorker.getRegistration(PUSH_WORKER_SCOPE);
  return existing ?? navigator.serviceWorker.register(PUSH_WORKER_URL, { scope: PUSH_WORKER_SCOPE });
}

/** How long a freshly registered worker is given to start before the tap is answered with a refusal. */
export const WORKER_START_MS = 10_000;

/**
 * Wait until the registration's own worker is active: a browser subscribes only an active worker.
 *
 * Never `navigator.serviceWorker.ready`: that waits for a worker whose scope holds *this page*, and the
 * phone's worker is scoped to `/phone/`, which does not hold `/phone.html`, so it would wait for ever
 * (review of PR 1339).
 */
export function workerActive(reg: Pick<ServiceWorkerRegistration, 'active' | 'installing' | 'waiting'>, waitMs = WORKER_START_MS): Promise<void> {
  if (reg.active) return Promise.resolve();
  const worker = reg.installing ?? reg.waiting;
  if (!worker) return Promise.reject(new Error('the notification worker did not install'));
  return new Promise<void>((resolve, reject) => {
    const timer = setTimeout(() => done(new Error('the notification worker did not start in time')), waitMs);
    function done(err?: Error): void {
      clearTimeout(timer);
      worker?.removeEventListener('statechange', check);
      if (err) reject(err);
      else resolve();
    }
    function check(): void {
      if (worker?.state === 'activated') done();
      else if (worker?.state === 'redundant') done(new Error('the notification worker was replaced before it started'));
    }
    worker.addEventListener('statechange', check);
    check();
  });
}

/** This phone's push address when it has one; null when it never subscribed (or cannot). */
export async function currentAddress(): Promise<PushAddress | null> {
  if (pushSupport()) return null;
  const reg = await navigator.serviceWorker.getRegistration(PUSH_WORKER_SCOPE);
  const sub = await reg?.pushManager.getSubscription();
  return sub ? addressOf(sub) : null;
}

/** The short id the PC lists a phone under: the first 16 hex of the SHA-256 of its push address. */
export async function deviceId(endpoint: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(endpoint));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('').slice(0, 16);
}

export type SubscribeResult =
  | { ok: true; address: PushAddress }
  | { ok: false; why: string };

/**
 * Ask Android for permission (once: it remembers the answer) and get this phone's push address for the PC's
 * key. Must run from a tap. An address made for another key (the PC's key was replaced) is dropped first.
 */
export async function subscribePush(publicKey: string): Promise<SubscribeResult> {
  const unsupported = pushSupport();
  if (unsupported) return { ok: false, why: unsupported };
  try {
    const permission = await Notification.requestPermission();
    if (permission !== 'granted') {
      return {
        ok: false,
        why: permission === 'denied'
          ? 'Notifications are blocked for Nova on this phone. Allow them in the phone\'s settings for this site, then turn this on again.'
          : 'The phone did not allow notifications, so nothing was turned on.',
      };
    }
    const reg = await registration();
    await workerActive(reg);
    const key = keyBytes(publicKey);
    let sub = await reg.pushManager.getSubscription();
    if (sub) {
      const had = sub.options.applicationServerKey ? new Uint8Array(sub.options.applicationServerKey) : null;
      const same = had != null && had.length === key.length && had.every((b, i) => b === key[i]);
      if (!same) {
        await sub.unsubscribe();
        sub = null;
      }
    }
    sub = sub ?? await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key });
    const address = addressOf(sub);
    return address ? { ok: true, address } : { ok: false, why: 'The phone gave no push address. Try again.' };
  } catch (err) {
    console.warn('[Nova phone] could not subscribe to notifications', err);
    return { ok: false, why: `The phone could not subscribe: ${err instanceof Error ? err.message : String(err)}` };
  }
}

/** Drop this phone's push address. The address it had, so the PC can forget it too; null when it had none. */
export async function unsubscribePush(): Promise<PushAddress | null> {
  if (pushSupport()) return null;
  const reg = await navigator.serviceWorker.getRegistration(PUSH_WORKER_SCOPE);
  const sub = await reg?.pushManager.getSubscription();
  if (!sub) return null;
  const address = addressOf(sub);
  await sub.unsubscribe();
  return address;
}

/** What the worker tells the page when a notification is tapped while the page is open: the screen to show. */
export interface PushOpenMessage {
  type: 'nova-open';
  hash: string;
}

/** Follow a tapped notification to its screen. Returns the function that stops listening. */
export function onPushOpen(open: (hash: string) => void): () => void {
  if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return () => undefined;
  const listen = (ev: MessageEvent): void => {
    const data = ev.data as Partial<PushOpenMessage> | null;
    if (data?.type === 'nova-open' && typeof data.hash === 'string' && data.hash.startsWith('#/')) open(data.hash);
  };
  navigator.serviceWorker.addEventListener('message', listen);
  return () => navigator.serviceWorker.removeEventListener('message', listen);
}
