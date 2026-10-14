/**
 * The stream the feed reads, watched from the Following page: its YouTube links (built only from an 11-character
 * video id, never from anything else the feed sends), the player's open / closed (kept in local storage, a per-window
 * convenience, open by default; storage that throws reads as open), and opening it elsewhere -- the desktop's own
 * small window or the system browser, a browser tab without the desktop. Schema: followed-traders.md, "On the desk".
 */
import { useSyncExternalStore } from 'react';
import { FOLLOWED_STREAM_KEY, YOUTUBE_EMBED_BASE, YOUTUBE_WATCH_BASE } from './constants';

const VIDEO_ID_RE = /^[A-Za-z0-9_-]{11}$/;

export function streamId(raw: string | null | undefined): string | null {
  return typeof raw === 'string' && VIDEO_ID_RE.test(raw) ? raw : null;
}

/** Muted to start (a page may not start a sound on its own); `enablejsapi` lets the mute switch command it. */
export function embedUrl(id: string): string {
  const q = new URLSearchParams({ autoplay: '1', mute: '1', playsinline: '1', rel: '0', enablejsapi: '1' });
  return `${YOUTUBE_EMBED_BASE}${id}?${q.toString()}`;
}

export function watchUrl(id: string): string {
  return `${YOUTUBE_WATCH_BASE}${id}`;
}

/** A command to the embedded player (YouTube's IFrame API over postMessage). */
export function playerCommand(func: 'mute' | 'unMute'): string {
  return JSON.stringify({ event: 'command', func, args: [] });
}

type Listener = () => void;
const listeners = new Set<Listener>();

function readOpen(): boolean {
  try {
    return window.localStorage.getItem(FOLLOWED_STREAM_KEY) !== 'closed';
  } catch {
    return true;
  }
}

let open = typeof window === 'undefined' ? true : readOpen();

export function setStreamOpen(next: boolean): void {
  try {
    window.localStorage.setItem(FOLLOWED_STREAM_KEY, next ? 'open' : 'closed');
  } catch {
    // Storage blocked: the switch still holds for this window.
  }
  if (next === open) return;
  open = next;
  listeners.forEach((l) => l());
}

export function useStreamOpen(): boolean {
  return useSyncExternalStore(
    (l) => { listeners.add(l); return () => { listeners.delete(l); }; },
    () => open,
    () => open,
  );
}

export function resetStreamForTests(): void {
  open = true;
}

/** The desktop's own small window when there is one; a browser tab otherwise. */
export function popOutStream(id: string): void {
  if (window.novaDesktop?.openStream) {
    void window.novaDesktop.openStream(id).catch((e: unknown) => console.warn('[nova] stream window failed', e));
    return;
  }
  window.open(watchUrl(id), '_blank', 'noopener,noreferrer');
}

export function openStreamOnYouTube(id: string): void {
  if (window.novaDesktop?.openExternal) {
    void window.novaDesktop.openExternal(watchUrl(id)).catch((e: unknown) => console.warn('[nova] open YouTube failed', e));
    return;
  }
  window.open(watchUrl(id), '_blank', 'noopener,noreferrer');
}
