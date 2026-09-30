/**
 * Share clips on the desk (ADR 039): one subscription per window to the
 * desktop app's clip view (`window.novaDesktop.clips`, electron/preload.cjs),
 * the operator's requests, and the little shared state the pieces need --
 * which CLIP chip is pointed at (the tab draws its frame), which clip's export
 * dialog is open, and the toasts. A browser desk has no bridge: clips are off
 * and every control says why.
 */
import { useSyncExternalStore } from 'react';
import { CLIP_NEED_DESKTOP } from './clipsConstants';
import { readClipsView, type ClipRowView, type ClipsView } from './clipsView';

export type ClipsBridge = NonNullable<NonNullable<Window['novaDesktop']>['clips']>;
export type ClipActResult = { ok: boolean; reason?: string; error?: string; [key: string]: unknown };

type Listener = () => void;
const listeners = new Set<Listener>();
let view: ClipsView | null = null;
let subscribed = false;
let hovered: string | null = null;
let dialogClipId: string | null = null;
let version = 0;

export type ClipToast = {
  id: string;
  kind: 'saved' | 'last' | 'exported' | 'failed';
  clip: ClipRowView | null;
  clipId: string;
  text: string;
  at: number;
};
let toasts: ClipToast[] = [];

const emit = () => {
  version += 1;
  for (const l of [...listeners]) l();
};

export const clipsBridge = (): ClipsBridge | null => window.novaDesktop?.clips ?? null;

function ensureSubscribed(): void {
  if (subscribed) return;
  const bridge = clipsBridge();
  if (!bridge) return;
  subscribed = true;
  bridge.subscribe((raw) => {
    const next = readClipsView(raw);
    if (next) {
      view = next;
      emit();
    }
  });
}

export function subscribeClips(listener: Listener): () => void {
  ensureSubscribed();
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export const getClipsVersion = (): number => version;
export const getClipsView = (): ClipsView | null => view;

/** `{desktop, view}`: whether this window can record clips at all, and the newest view (null until it arrives). */
/** The desk's clip view; `version` changes with every view, toast or request (an effect's dependency). */
export function useClips(): { desktop: boolean; view: ClipsView | null; version: number } {
  const version = useSyncExternalStore(subscribeClips, getClipsVersion, () => 0);
  return { desktop: clipsBridge() !== null, view, version };
}

export async function actClip(request: Record<string, unknown>): Promise<ClipActResult> {
  const bridge = clipsBridge();
  if (!bridge) return { ok: false, reason: 'CLIP_NO_DESKTOP', error: CLIP_NEED_DESKTOP };
  try {
    const res = (await bridge.act(request)) as ClipActResult | null;
    return res && typeof res === 'object' ? res : { ok: false, error: 'The desktop app sent no answer.' };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }
}

/** This window's Trader tab, for the main process (clipTabReport.ts builds it). */
export function reportClipTab(report: Record<string, unknown>): void {
  clipsBridge()?.report(report);
}

// ── The CLIP chip being pointed at: the tab it films draws its red frame. ──
export const getHoveredClip = (): string | null => hovered;
export function setHoveredClip(clipId: string | null): void {
  if (hovered === clipId) return;
  hovered = clipId;
  emit();
}

// ── The export dialog (one at a time, in the main desk). ──
export const getExportDialogClip = (): string | null => dialogClipId;
export function openClipExport(clipId: string): void {
  dialogClipId = clipId;
  emit();
}
export function closeClipExport(): void {
  dialogClipId = null;
  emit();
}

// ── Records opens on its Video clips list when a link asked for it. ──
let listRequested = false;
export function requestClipsList(): void {
  listRequested = true;
  emit();
}
/** True once after a link asked for the list (Records reads it when it mounts or hears the change). */
export function takeClipsListRequest(): boolean {
  const asked = listRequested;
  listRequested = false;
  return asked;
}

// ── Toasts: a stopped clip, a saved one, a finished or failed export. ──
export const getClipToasts = (): ClipToast[] => toasts;
export function pushClipToast(toast: Omit<ClipToast, 'id' | 'at'>): void {
  const at = Date.now();
  toasts = [{ ...toast, id: `${toast.kind}-${toast.clipId}-${at}`, at }, ...toasts.filter((t) => t.clipId !== toast.clipId)].slice(0, 4);
  emit();
}
export function dismissClipToast(id: string): void {
  toasts = toasts.filter((t) => t.id !== id);
  emit();
}

export function _resetClipsStoreForTests(): void {
  view = null;
  subscribed = false;
  hovered = null;
  dialogClipId = null;
  toasts = [];
  listRequested = false;
  listeners.clear();
  version = 0;
}
