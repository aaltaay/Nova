/** One short ping when the bot raises a proposal (a setup near its trigger with
 * the tape saying go). Its own switch and volume, separate from HOD Momo's, live in
 * sound/ (the header's sound menu sets them too); the header mute silences it too. */
import {
  DESK_TONE_SETUPS,
  deskSoundAudible,
  deskSoundOn,
  playDeskTone,
  resetDeskSoundsForTests,
  resetDeskTonesForTests,
  setDeskSoundOn,
  subscribeDeskSounds,
} from '../sound';

type Listener = (enabled: boolean) => void;

const heard = new Set<string>();

export function isSetupsSoundEnabled(): boolean {
  return deskSoundOn('setups');
}

export function setSetupsSoundEnabled(next: boolean): void {
  setDeskSoundOn('setups', next);
}

export function subscribeSetupsSound(fn: Listener): () => void {
  return subscribeDeskSounds(() => fn(deskSoundOn('setups')));
}

/** Ping once per proposal id. Returns what happened, for tests. */
export function noteSetupProposal(id: string): 'pinged' | 'duplicate' | 'muted' | 'silent' {
  if (heard.has(id)) return 'duplicate';
  heard.add(id);
  if (!deskSoundAudible('setups')) return 'muted';
  return playDeskTone('setups', DESK_TONE_SETUPS) ? 'pinged' : 'silent';
}

export function resetSetupsSoundForTests(): void {
  heard.clear();
  resetDeskTonesForTests();
  resetDeskSoundsForTests();
}
