/**
 * Each desk sound's own switch and volume, in one place (operator ask, 2026-11-05: "a dropdown menu controlling the
 * other sounds"). The header's sound menu and each source's own button are the same setting here, and a change in one
 * window reaches the others -- the Top 9 pop-up too -- through the `storage` event. The header mute (deskMute.ts) sits
 * above all of it.
 *
 * Schema: architecture/schema/desk-ops.md, "The desk's voice and the header mute". Each switch keeps the key and shape
 * it always had; the stream's lives in memory, off to start, so a stream never starts talking on its own.
 */
import { useSyncExternalStore } from 'react';
import { parseBoolFlag, readPref, writePref } from '../utils/prefStore';
import {
  DESK_SOUND_IDS,
  DESK_SOUND_KEYS,
  DESK_SOUND_LEVEL_DEFAULTS,
  DESK_SOUND_LEVEL_MAX,
  DESK_SOUND_LEVELS_KEY,
  type DeskSoundId,
} from './constants';
import { isDeskMuted } from './deskMute';

type Listener = () => void;
type Levels = Record<DeskSoundId, number>;

interface StoredSwitch {
  key: string;
  read(): boolean;
  write(on: boolean): void;
}

function hasStorage(): boolean {
  return typeof localStorage !== 'undefined';
}

function prefSwitch(key: string): StoredSwitch {
  return {
    key,
    read: () => (hasStorage() ? readPref(key, true, parseBoolFlag) : true),
    write: (on) => {
      if (hasStorage()) writePref(key, on);
    },
  };
}

/** A switch stored as a bare word: `on` is what it reads as on, `off` what it writes for off. */
function rawSwitch(key: string, read: (raw: string | null) => boolean, on: string, off: string): StoredSwitch {
  return {
    key,
    read: () => {
      try {
        return read(localStorage.getItem(key));
      } catch {
        return true; // no storage: the sound stays on
      }
    },
    write: (next) => {
      try {
        localStorage.setItem(key, next ? on : off);
      } catch {
        // Storage blocked: the switch still holds for this window.
      }
    },
  };
}

const SWITCHES: Partial<Record<DeskSoundId, StoredSwitch>> = {
  hod: prefSwitch(DESK_SOUND_KEYS.hod),
  setups: rawSwitch(DESK_SOUND_KEYS.setups, raw => raw !== 'off', 'on', 'off'),
  topNine: prefSwitch(DESK_SOUND_KEYS.topNine),
  voice: prefSwitch(DESK_SOUND_KEYS.voice),
  calls: prefSwitch(DESK_SOUND_KEYS.calls),
  // Stored the other way round: 1 means the alarm is muted.
  alarm: rawSwitch(DESK_SOUND_KEYS.alarm, raw => !(raw === '1' || raw === 'true'), '0', '1'),
};

function parseLevels(raw: unknown): Partial<Levels> | null {
  if (!raw || typeof raw !== 'object') return null;
  const levels: Partial<Levels> = {};
  for (const id of DESK_SOUND_IDS) {
    const n = (raw as Record<string, unknown>)[id];
    if (Number.isInteger(n) && (n as number) >= 0 && (n as number) <= DESK_SOUND_LEVEL_MAX) levels[id] = n as number;
  }
  return levels;
}

function readLevels(): Levels {
  const stored = hasStorage() ? readPref<Partial<Levels> | null>(DESK_SOUND_LEVELS_KEY, null, parseLevels) : null;
  return { ...DESK_SOUND_LEVEL_DEFAULTS, ...stored };
}

function readSwitches(): Record<DeskSoundId, boolean> {
  const read = {} as Record<DeskSoundId, boolean>;
  for (const id of DESK_SOUND_IDS) read[id] = SWITCHES[id]?.read() ?? false;
  return read;
}

const listeners = new Set<Listener>();
let on = readSwitches();
let levels = readLevels();

function emit(): void {
  for (const fn of listeners) fn();
}

if (typeof window !== 'undefined') {
  // Another window moved a switch or a slider: this one follows, so no window plays the old setting.
  window.addEventListener('storage', (ev) => {
    if (ev.key === DESK_SOUND_LEVELS_KEY) {
      levels = readLevels();
      emit();
      return;
    }
    const id = DESK_SOUND_IDS.find(x => SWITCHES[x]?.key === ev.key);
    if (!id) return;
    const next = SWITCHES[id]?.read() ?? false;
    if (next === on[id]) return;
    on = { ...on, [id]: next };
    emit();
  });
}

export function deskSoundOn(id: DeskSoundId): boolean {
  return on[id];
}

export function setDeskSoundOn(id: DeskSoundId, next: boolean): void {
  if (next === on[id]) return;
  on = { ...on, [id]: next };
  SWITCHES[id]?.write(next);
  emit();
}

export function deskSoundLevel(id: DeskSoundId): number {
  return levels[id];
}

export function setDeskSoundLevel(id: DeskSoundId, next: number): void {
  const level = Math.max(0, Math.min(DESK_SOUND_LEVEL_MAX, Math.round(next)));
  if (level === levels[id]) return;
  levels = { ...levels, [id]: level };
  if (hasStorage()) writePref(DESK_SOUND_LEVELS_KEY, levels);
  emit();
}

/** Whether the sound would be heard: its switch, its volume and the header mute. */
export function deskSoundAudible(id: DeskSoundId): boolean {
  return on[id] && levels[id] > 0 && !isDeskMuted();
}

/** A tone's peak at the sound's volume: `gain` is its peak at the default level. */
export function deskSoundGain(id: DeskSoundId, gain: number): number {
  return gain * levels[id] / DESK_SOUND_LEVEL_DEFAULTS[id];
}

export function subscribeDeskSounds(fn: Listener): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

export function useDeskSoundOn(id: DeskSoundId): boolean {
  return useSyncExternalStore(subscribeDeskSounds, () => on[id], () => on[id]);
}

export function useDeskSoundLevel(id: DeskSoundId): number {
  return useSyncExternalStore(subscribeDeskSounds, () => levels[id], () => levels[id]);
}

/** Test-only: re-read every stored switch and level. */
export function resetDeskSoundsForTests(): void {
  on = readSwitches();
  levels = readLevels();
}
