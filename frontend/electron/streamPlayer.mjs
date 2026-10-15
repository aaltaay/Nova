/**
 * The followed traders' live stream on the desktop (Following page, 2026-10-13), YouTube only:
 *
 * - The installed desk is a page loaded from a file, which sends no Referer, and YouTube refuses an embedded player
 *   without one ("Error 153"). `attachYouTubeReferer` names Nova's own site as the Referer on requests to YouTube's
 *   player hosts that carry none -- nothing else is touched.
 * - `openStreamWindow` shows one stream in a small window of its own (Pop out), built only from an 11-character
 *   video id; it never runs Nova code (no preload) and opens nothing else.
 * - YouTube asks this desk's network to sign in before it plays ("confirm you're not a bot"). `openYouTubeSignIn`
 *   opens Google's own sign-in page in a window of its own on the desk's session, where the operator signs in
 *   themselves; Nova never sees what is typed there. The player's own Sign in button is sent there too
 *   (`isYouTubeSignInUrl`). The window closes as soon as it is on YouTube signed in -- read from the session's own
 *   YouTube login cookie, so a desk already signed in closes it at once -- and the desk's players reload.
 * - The players are YouTube's ordinary embed (`www.youtube.com/embed`), not the privacy-enhanced one: that one never
 *   carries the YouTube sign-in, so it asked to sign in again however often the operator did (operator report,
 *   2026-10-15). The sign-in lives in the desk's persistent session, so it survives restarts until Google ends it.
 *
 * Schema: architecture/schema/followed-traders.md, "On the desk". Owner: main.mjs wires it.
 */

const VIDEO_ID_RE = /^[A-Za-z0-9_-]{11}$/;
/** Nova's public site: who is asking, for YouTube's embed check. */
export const STREAM_REFERER = 'https://nova.altaystudio.com/';
export const YOUTUBE_PLAYER_URLS = ['https://www.youtube-nocookie.com/*', 'https://www.youtube.com/*'];
const PLAYER_HOSTS = new Set(['www.youtube-nocookie.com', 'www.youtube.com']);
/** YouTube's ordinary embed: the one that carries the desk session's YouTube sign-in. */
export const STREAM_EMBED_BASE = 'https://www.youtube.com/embed/';

export function isStreamVideoId(id) {
  return typeof id === 'string' && VIDEO_ID_RE.test(id);
}

export function streamEmbedUrl(id) {
  return `${STREAM_EMBED_BASE}${id}?autoplay=1&playsinline=1&rel=0`;
}

/** Headers for a request to YouTube's player hosts: a Referer when it has none, never a replaced one. */
export function withReferer(url, headers) {
  let host = '';
  try {
    host = new URL(url).hostname;
  } catch {
    return headers;
  }
  if (!PLAYER_HOSTS.has(host)) return headers;
  const has = Object.keys(headers).some((k) => k.toLowerCase() === 'referer');
  return has ? headers : { ...headers, Referer: STREAM_REFERER };
}

export function attachYouTubeReferer(session) {
  session.webRequest.onBeforeSendHeaders({ urls: YOUTUBE_PLAYER_URLS }, (details, callback) => {
    callback({ requestHeaders: withReferer(details.url, details.requestHeaders) });
  });
}

let streamWindow = null;

/** One small window for the stream; a second Pop out shows the new stream in it. */
export async function openStreamWindow(BrowserWindow, id, { icon } = {}) {
  if (!isStreamVideoId(id)) throw new Error('Not a stream id');
  if (!streamWindow || streamWindow.isDestroyed()) {
    streamWindow = new BrowserWindow({
      width: 640,
      height: 380,
      minWidth: 320,
      minHeight: 200,
      title: 'Following · live stream',
      backgroundColor: '#000000',
      icon,
      autoHideMenuBar: true,
      webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true },
    });
    streamWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
    streamWindow.webContents.on('will-navigate', (event, url) => {
      if (!url.startsWith(STREAM_EMBED_BASE)) event.preventDefault();
    });
    streamWindow.on('closed', () => {
      streamWindow = null;
    });
  }
  await streamWindow.loadURL(streamEmbedUrl(id));
  streamWindow.show();
  streamWindow.focus();
  return true;
}

/** Google's sign-in for YouTube, back to YouTube when it is done. */
export const YOUTUBE_SIGN_IN_URL =
  'https://accounts.google.com/ServiceLogin?service=youtube&uilel=3&passive=true&continue=https%3A%2F%2Fwww.youtube.com%2F';

function hostOf(url) {
  try {
    return new URL(url).hostname;
  } catch {
    return '';
  }
}

function isGoogleOrYouTube(host) {
  return host === 'google.com' || host.endsWith('.google.com') || host === 'youtube.com' || host.endsWith('.youtube.com');
}

/** A popup the player opens to sign in: Google's accounts pages, or YouTube's own sign-in. */
export function isYouTubeSignInUrl(url) {
  const host = hostOf(url);
  if (host === 'accounts.google.com') return true;
  if (host !== 'www.youtube.com' && host !== 'youtube.com') return false;
  return new URL(url).pathname.startsWith('/signin') || new URL(url).pathname.startsWith('/ServiceLogin');
}

/** YouTube's own cookies that exist only while signed in. */
const YOUTUBE_SIGNED_IN_COOKIES = ['LOGIN_INFO', 'SID', '__Secure-3PSID'];

/** Is this session signed in to YouTube? Read from its cookies; a cookie store that fails reads as not signed in. */
export async function isSignedInToYouTube(session) {
  try {
    const cookies = await session.cookies.get({ url: 'https://www.youtube.com/' });
    return cookies.some((c) => YOUTUBE_SIGNED_IN_COOKIES.includes(c.name));
  } catch (err) {
    console.warn('[nova] YouTube sign-in check failed', err);
    return false;
  }
}

let signInWindow = null;

/** One sign-in window; `onDone(signedIn)` runs when it closes. */
export function openYouTubeSignIn(BrowserWindow, { icon, onDone } = {}) {
  if (signInWindow && !signInWindow.isDestroyed()) {
    signInWindow.focus();
    return true;
  }
  let signedIn = false;
  const win = new BrowserWindow({
    width: 520,
    height: 720,
    title: 'Sign in to YouTube',
    icon,
    autoHideMenuBar: true,
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true },
  });
  signInWindow = win;
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  win.webContents.on('will-navigate', (event, url) => {
    if (!isGoogleOrYouTube(hostOf(url))) event.preventDefault();
  });
  // Google sends a desk that is already signed in straight to YouTube, with no sign-in page on the way.
  win.webContents.on('did-navigate', (_event, url) => {
    const host = hostOf(url);
    if (host !== 'www.youtube.com' && host !== 'youtube.com') return;
    void isSignedInToYouTube(win.webContents.session).then((yes) => {
      if (!yes || win.isDestroyed()) return;
      signedIn = true;
      win.close();
    });
  });
  win.on('closed', () => {
    signInWindow = null;
    onDone?.(signedIn);
  });
  void win.loadURL(YOUTUBE_SIGN_IN_URL).catch((err) => console.error('[nova] YouTube sign-in failed to load', err));
  return true;
}
