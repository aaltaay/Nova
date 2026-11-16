/**
 * The chart's ping (ADR 037): one short sound per call -- ENTER NOW, SELL NOW, COVER NOW, a broken level -- keyed on
 * the call's id, so a call that stays on screen pings once per page. Its own switch and volume live in
 * sound/ (`nova.stockRead.sound`, shared by every Trader tab; the header's sound menu sets them too). The header
 * mute silences it too.
 */
import {
  DESK_TONE_CALL,
  deskSoundAudible,
  deskSoundOn,
  playDeskTone,
  resetDeskSoundsForTests,
  resetDeskTonesForTests,
  setDeskSoundOn,
  subscribeDeskSounds,
} from '../sound';
import type { CallTone } from './momentModel';

type Listener = () => void;

/** Two notes for a call to act (enter, sell), one for a trade that is done. */
const NOTES: Partial<Record<CallTone, number[]>> = {
  go: [880, 1175],
  target: [988, 740],
  stop: [659, 440],
  done: [1047],
};

const heard = new Set<string>();

export function isStockReadSoundOn(): boolean {
  return deskSoundOn('calls');
}

export function setStockReadSound(next: boolean): void {
  setDeskSoundOn('calls', next);
}

export function subscribeStockReadSound(fn: Listener): () => void {
  return subscribeDeskSounds(fn);
}

/** Ping once per call id. Returns what happened, for tests. */
export function pingCall(id: string, tone: CallTone): 'pinged' | 'duplicate' | 'muted' | 'silent' {
  if (heard.has(id)) return 'duplicate';
  heard.add(id);
  if (!deskSoundAudible('calls')) return 'muted';
  const notes = NOTES[tone];
  return notes && playDeskTone('calls', { ...DESK_TONE_CALL, hz: notes }) ? 'pinged' : 'silent';
}

export function resetStockReadSoundForTests(): void {
  heard.clear();
  resetDeskTonesForTests();
  resetDeskSoundsForTests();
}
