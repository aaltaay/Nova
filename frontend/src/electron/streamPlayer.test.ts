/**
 * The followed traders' stream on the desktop: a Referer only on YouTube's player hosts, never a replaced one, a
 * Pop out window only for an 11-character video id, the embed that carries the sign-in, and a sign-in window that
 * closes once the session is signed in to YouTube.
 */
import { describe, expect, it, vi } from 'vitest';
import {
  STREAM_REFERER,
  YOUTUBE_SIGN_IN_URL,
  attachYouTubeReferer,
  isSignedInToYouTube,
  isStreamVideoId,
  isYouTubeSignInUrl,
  openStreamWindow,
  openYouTubeSignIn,
  streamEmbedUrl,
  withReferer,
} from '../../electron/streamPlayer.mjs';

describe('stream player', () => {
  it('adds a Referer to YouTube player requests that carry none, and touches nothing else', () => {
    expect(withReferer('https://www.youtube-nocookie.com/embed/R5YIugCJar0', { Accept: '*/*' }))
      .toEqual({ Accept: '*/*', Referer: STREAM_REFERER });
    expect(withReferer('https://www.youtube.com/iframe_api', {})).toEqual({ Referer: STREAM_REFERER });
    expect(withReferer('https://www.youtube.com/x', { referer: 'http://127.0.0.1:5173/' }))
      .toEqual({ referer: 'http://127.0.0.1:5173/' });
    expect(withReferer('https://127.0.0.1:8000/api/ibkr/status', {})).toEqual({});
    expect(withReferer('https://evil.example/www.youtube.com', {})).toEqual({});
    expect(withReferer('not a url', { a: '1' })).toEqual({ a: '1' });
  });

  it('hooks only the player hosts', () => {
    const onBeforeSendHeaders = vi.fn();
    attachYouTubeReferer({ webRequest: { onBeforeSendHeaders } });
    const [filter, listener] = onBeforeSendHeaders.mock.calls[0];
    expect(filter.urls).toEqual(['https://www.youtube-nocookie.com/*', 'https://www.youtube.com/*']);
    const callback = vi.fn();
    listener({ url: 'https://www.youtube-nocookie.com/embed/R5YIugCJar0', requestHeaders: {} }, callback);
    expect(callback).toHaveBeenCalledWith({ requestHeaders: { Referer: STREAM_REFERER } });
  });

  it('opens a window only for a YouTube video id', async () => {
    expect(isStreamVideoId('R5YIugCJar0')).toBe(true);
    expect(isStreamVideoId('../../x')).toBe(false);
    expect(isStreamVideoId('R5YIugCJar0x')).toBe(false);
    const loadURL = vi.fn(async () => undefined);
    const win = {
      isDestroyed: () => false, show: vi.fn(), focus: vi.fn(), loadURL, on: vi.fn(),
      webContents: { setWindowOpenHandler: vi.fn(), on: vi.fn() },
    };
    const BrowserWindow = vi.fn(function BrowserWindow() { return win; });
    await expect(openStreamWindow(BrowserWindow, 'javascript:x')).rejects.toThrow('Not a stream id');
    expect(BrowserWindow).not.toHaveBeenCalled();
    await openStreamWindow(BrowserWindow, 'R5YIugCJar0');
    expect(loadURL).toHaveBeenCalledWith(streamEmbedUrl('R5YIugCJar0'));
    expect(win.webContents.setWindowOpenHandler.mock.calls[0][0]()).toEqual({ action: 'deny' });
  });

  it('plays YouTube’s ordinary embed, the one that carries the desk’s YouTube sign-in', () => {
    expect(streamEmbedUrl('R5YIugCJar0')).toBe('https://www.youtube.com/embed/R5YIugCJar0?autoplay=1&playsinline=1&rel=0');
  });

  it('reads the sign-in from the session’s YouTube login cookie', async () => {
    const session = (names: string[]) => ({ cookies: { get: vi.fn(async () => names.map((name) => ({ name }))) } });
    expect(await isSignedInToYouTube(session(['VISITOR_INFO1_LIVE', 'LOGIN_INFO']))).toBe(true);
    expect(await isSignedInToYouTube(session(['__Secure-3PSID']))).toBe(true);
    expect(await isSignedInToYouTube(session(['VISITOR_INFO1_LIVE', 'YSC']))).toBe(false);
    const broken = { cookies: { get: vi.fn(async () => { throw new Error('locked'); }) } };
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    expect(await isSignedInToYouTube(broken)).toBe(false);
    warn.mockRestore();
  });

  function signInHarness(cookieNames: string[]) {
    const handlers: Record<string, (...a: unknown[]) => void> = {};
    const nav: Record<string, (...a: unknown[]) => void> = {};
    const jar = { names: cookieNames };
    let destroyed = false;
    const win = {
      isDestroyed: () => destroyed, focus: vi.fn(),
      close: vi.fn(() => { destroyed = true; handlers.closed(); }),
      loadURL: vi.fn(async () => undefined), on: (ev: string, fn: () => void) => { handlers[ev] = fn; },
      webContents: {
        setWindowOpenHandler: vi.fn(), on: (ev: string, fn: () => void) => { nav[ev] = fn; },
        session: { cookies: { get: vi.fn(async () => jar.names.map((name) => ({ name }))) } },
      },
    };
    const BrowserWindow = vi.fn(function BrowserWindow() { return win; });
    const onDone = vi.fn();
    openYouTubeSignIn(BrowserWindow, { onDone });
    return { win, nav, jar, onDone, BrowserWindow };
  }

  it('sends the player’s sign-in popup to Google’s page in a window of its own, and says when it is done', async () => {
    expect(isYouTubeSignInUrl('https://accounts.google.com/ServiceLogin?service=youtube')).toBe(true);
    expect(isYouTubeSignInUrl('https://www.youtube.com/signin?action_handle_signin=true')).toBe(true);
    expect(isYouTubeSignInUrl('https://www.youtube.com/watch?v=R5YIugCJar0')).toBe(false);
    expect(isYouTubeSignInUrl('https://accounts.google.com.evil.example/x')).toBe(false);
    const { win, nav, jar, onDone } = signInHarness([]);
    expect(win.loadURL).toHaveBeenCalledWith(YOUTUBE_SIGN_IN_URL);
    const blocked = { preventDefault: vi.fn() };
    nav['will-navigate'](blocked, 'https://evil.example/phish');
    expect(blocked.preventDefault).toHaveBeenCalled();
    nav['did-navigate']({}, 'https://accounts.google.com/v3/signin/identifier');
    // On YouTube but not signed in yet (the operator went back): the window stays.
    nav['did-navigate']({}, 'https://www.youtube.com/');
    await vi.waitFor(() => expect(win.webContents.session.cookies.get).toHaveBeenCalled());
    expect(win.close).not.toHaveBeenCalled();
    jar.names = ['LOGIN_INFO'];
    nav['did-navigate']({}, 'https://www.youtube.com/');
    await vi.waitFor(() => expect(win.close).toHaveBeenCalled());
    expect(onDone).toHaveBeenCalledWith(true);
  });

  it('closes at once for a desk already signed in, which Google sends straight to YouTube', async () => {
    const { win, nav, onDone } = signInHarness(['SID', 'LOGIN_INFO']);
    nav['did-navigate']({}, 'https://www.youtube.com/');
    await vi.waitFor(() => expect(win.close).toHaveBeenCalled());
    expect(onDone).toHaveBeenCalledWith(true);
  });
});
