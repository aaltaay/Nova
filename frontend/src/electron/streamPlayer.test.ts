/**
 * The followed traders' stream on the desktop: a Referer only on YouTube's player hosts, never a replaced one, and a
 * Pop out window only for an 11-character video id.
 */
import { describe, expect, it, vi } from 'vitest';
import {
  STREAM_REFERER,
  YOUTUBE_SIGN_IN_URL,
  attachYouTubeReferer,
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

  it('sends the player’s sign-in popup to Google’s page in a window of its own, and says when it is done', () => {
    expect(isYouTubeSignInUrl('https://accounts.google.com/ServiceLogin?service=youtube')).toBe(true);
    expect(isYouTubeSignInUrl('https://www.youtube.com/signin?action_handle_signin=true')).toBe(true);
    expect(isYouTubeSignInUrl('https://www.youtube.com/watch?v=R5YIugCJar0')).toBe(false);
    expect(isYouTubeSignInUrl('https://accounts.google.com.evil.example/x')).toBe(false);
    const handlers: Record<string, (...a: unknown[]) => void> = {};
    const nav: Record<string, (...a: unknown[]) => void> = {};
    const win = {
      isDestroyed: () => false, focus: vi.fn(), close: vi.fn(() => handlers.closed()),
      loadURL: vi.fn(async () => undefined), on: (ev: string, fn: () => void) => { handlers[ev] = fn; },
      webContents: { setWindowOpenHandler: vi.fn(), on: (ev: string, fn: () => void) => { nav[ev] = fn; } },
    };
    const BrowserWindow = vi.fn(function BrowserWindow() { return win; });
    const onDone = vi.fn();
    openYouTubeSignIn(BrowserWindow, { onDone });
    expect(win.loadURL).toHaveBeenCalledWith(YOUTUBE_SIGN_IN_URL);
    const blocked = { preventDefault: vi.fn() };
    nav['will-navigate'](blocked, 'https://evil.example/phish');
    expect(blocked.preventDefault).toHaveBeenCalled();
    nav['did-navigate']({}, 'https://accounts.google.com/v3/signin/identifier');
    nav['did-navigate']({}, 'https://www.youtube.com/');
    expect(win.close).toHaveBeenCalled();
    expect(onDone).toHaveBeenCalledWith(true);
  });
});
