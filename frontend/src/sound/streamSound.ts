/**
 * The stream's sound (the sound menu's YouTube row): one switch and one volume for whichever player has it -- the
 * desktop pop-out while it is open, otherwise the in-page player (followed_traders/StreamPlayer.tsx). The switch starts
 * off and goes off with its player, so the next one starts muted; the pop-out plays with sound, as it always has.
 *
 * Schema: architecture/schema/desk-ops.md, "The YouTube row". The pop-out runs no Nova code: the desktop app applies
 * what it is told here (electron/deskSound.mjs).
 */
import { useSyncExternalStore } from 'react';
import { subscribeDeskMute } from './deskMute';
import { deskSoundLevel, deskSoundOn, setDeskSoundOn, subscribeDeskSounds } from './deskSounds';

export type StreamPlayerState = 'none' | 'offline' | 'live';

type Listener = () => void;

const listeners = new Set<Listener>();
let player: StreamPlayerState = 'none';
let popOutOpen = false;
let told: string | null = null;

function emit(): void {
  for (const fn of listeners) fn();
}

function subscribe(fn: Listener): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

export function setStreamPlayerState(next: StreamPlayerState): void {
  if (next === player) return;
  player = next;
  if (next !== 'live') quietStream();
  emit();
}

/** The player is starting over: its sound starts muted again. The pop-out's is not touched. */
export function quietStream(): void {
  if (!popOutOpen) setDeskSoundOn('stream', false);
}

// The header mute ends the in-page player's sound until it is asked for again; the pop-out comes back with the desk.
subscribeDeskMute((nowMuted) => {
  if (nowMuted) quietStream();
});

function notePopOut(open: boolean, on: boolean): void {
  popOutOpen = open;
  told = null; // a page just loaded in the pop-out: it plays at YouTube's volume until told the row's
  setDeskSoundOn('stream', on);
  tellDesktop();
  emit();
}

/** Another page moved the pop-out's switch: this row follows, with nothing to tell. An in-page switch stays its page's. */
function followPopOut(on: boolean): void {
  if (!popOutOpen) return;
  told = JSON.stringify({ on, level: deskSoundLevel('stream') });
  setDeskSoundOn('stream', on);
}

/** The desktop app applies the row to the pop-out; it hears only what changed. */
function tellDesktop(): void {
  const sound = { on: deskSoundOn('stream'), level: deskSoundLevel('stream') };
  const said = JSON.stringify(sound);
  if (said === told) return;
  told = said;
  try {
    window.novaDesktop?.setStreamSound?.(sound);
  } catch (err) {
    console.warn('[nova] the desktop app did not take the stream sound', err);
  }
}

export function wireStreamWindow(): () => void {
  const desktop = window.novaDesktop;
  if (!desktop?.onStreamWindow) return () => undefined;
  const offWindow = desktop.onStreamWindow(open => notePopOut(open, open));
  const offSwitch = desktop.onStreamSwitch?.(followPopOut);
  const offSounds = subscribeDeskSounds(tellDesktop);
  // A page reloaded under an open pop-out picks up where it was.
  void desktop.streamWindowState?.()
    .then((state) => {
      if (state.open) notePopOut(true, state.on);
    })
    .catch((err: unknown) => console.warn('[nova] could not read the stream window', err));
  return () => {
    offWindow();
    offSwitch?.();
    offSounds();
  };
}

export function useStreamPlayerState(): StreamPlayerState {
  return useSyncExternalStore(subscribe, () => player, () => player);
}

export function useStreamPopOutOpen(): boolean {
  return useSyncExternalStore(subscribe, () => popOutOpen, () => popOutOpen);
}

/** Test-only. */
export function resetStreamSoundForTests(): void {
  player = 'none';
  popOutOpen = false;
  told = null;
}
