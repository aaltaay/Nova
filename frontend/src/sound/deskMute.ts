/**
 * The header's mute (operator ask, 2026-10-14: "I do really want to master the mute button on the header"):
 * one switch for every sound Nova makes. Each sound -- the voice, the HOD Momo, Setups and Trader pings, the
 * Nova OS alarm, the TraderTV stream -- asks `isDeskMuted()` before it plays, under its own switch.
 *
 * Schema: architecture/schema/desk-ops.md, "The desk's voice and the header mute". `nova.desk.sound.muted`
 * is shared by every window: a click in one reaches the others through the `storage` event, and the desktop
 * app mutes every window's audio with it (electron/deskSound.mjs).
 */
import { useSyncExternalStore } from 'react';
import { parseBoolFlag, readPref, writePref } from '../utils/prefStore';
import { DESK_SOUND_MUTED_DEFAULT, DESK_SOUND_MUTED_KEY } from './constants';

type Listener = (muted: boolean) => void;

const listeners = new Set<Listener>();

function readMuted(): boolean {
  if (typeof localStorage === 'undefined') return DESK_SOUND_MUTED_DEFAULT;
  return readPref(DESK_SOUND_MUTED_KEY, DESK_SOUND_MUTED_DEFAULT, parseBoolFlag);
}

let muted = readMuted();

/** The desktop app mutes every Nova window with the switch; a browser has no such door. */
function tellDesktop(): void {
  try {
    window.novaDesktop?.setSoundMuted?.(muted);
  } catch (err) {
    console.warn('[nova] the desktop app did not take the mute', err);
  }
}

function emit(): void {
  tellDesktop();
  for (const fn of listeners) fn(muted);
}

if (typeof window !== 'undefined') {
  // Another window clicked the mute: this one follows, so no window keeps talking.
  window.addEventListener('storage', (ev) => {
    if (ev.key !== DESK_SOUND_MUTED_KEY) return;
    const next = readMuted();
    if (next === muted) return;
    muted = next;
    emit();
  });
  tellDesktop();
}

export function isDeskMuted(): boolean {
  return muted;
}

export function setDeskMuted(next: boolean): void {
  if (next === muted) return;
  muted = next;
  if (typeof localStorage !== 'undefined') writePref(DESK_SOUND_MUTED_KEY, next);
  emit();
}

export function subscribeDeskMute(fn: Listener): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

export function useDeskMuted(): boolean {
  return useSyncExternalStore(subscribeDeskMute, isDeskMuted);
}

/** Test-only: re-read the stored switch. */
export function resetDeskMuteForTests(): void {
  muted = readMuted();
}
