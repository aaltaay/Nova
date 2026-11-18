/*
 * Nova on the phone: the notification worker (ADR 070, amendment 2026-11-18).
 *
 * It does two things. It shows what the PC pushed, with the page closed and the phone locked. And a tap
 * opens Nova on the screen the notification names. Its scope is /phone/, so it controls no page and
 * answers no request: it has no fetch handler, caches nothing, and decides nothing about what is sent.
 *
 * A push is JSON the PC scrambled for this phone alone: { title, body, tag, hash, at }.
 */
const PAGE = '/phone.html';

self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

function readPush(event) {
  try {
    const data = event.data ? event.data.json() : null;
    if (data && typeof data.title === 'string') return data;
  } catch (err) {
    console.warn('[Nova] a push could not be read', err);
  }
  // The browser requires every push to be shown: say that one arrived that could not be read.
  return { title: 'Nova', body: 'A notification arrived that this phone could not read.', tag: 'nova-unread', hash: '#/home' };
}

self.addEventListener('push', (event) => {
  const data = readPush(event);
  const hash = typeof data.hash === 'string' && data.hash.startsWith('#/') ? data.hash : '#/home';
  event.waitUntil(self.registration.showNotification(data.title, {
    body: typeof data.body === 'string' ? data.body : '',
    // One notification per tag: a newer one about the same stock replaces the older.
    tag: typeof data.tag === 'string' ? data.tag : undefined,
    renotify: typeof data.tag === 'string',
    icon: '/phone/icon-192.png',
    badge: '/phone/icon-192.png',
    timestamp: typeof data.at === 'number' ? data.at * 1000 : Date.now(),
    data: { hash },
  }));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const hash = (event.notification.data && event.notification.data.hash) || '#/home';
  event.waitUntil((async () => {
    const pages = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    const open = pages.find((c) => new URL(c.url).pathname === PAGE);
    if (open) {
      // The page is not this worker's to navigate: tell it the screen, and bring it to the front.
      open.postMessage({ type: 'nova-open', hash });
      await open.focus();
      return;
    }
    await self.clients.openWindow(PAGE + hash);
  })());
});
