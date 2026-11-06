/** The pop-up's sounds (operator ask, 2026-10-27: "When the menu switches ... I need to hear the sound"):
 * a two-note chime when a stock on screen moves up or comes in, at most once per TOP_NINE_CHIME_COOLDOWN_MS --
 * a switch inside that window stays quiet, it is not queued -- and three short beeps when one halts, which no
 * cooldown holds back. Its own switch and volume live in sound/ (on by default; the header's sound menu sets them
 * too); the header mute silences both. */
import { DESK_TONE_TOP_NINE_CHIME, DESK_TONE_TOP_NINE_HALT, deskSoundAudible, playDeskTone } from '../sound';
import { TOP_NINE_CHIME_COOLDOWN_MS } from './topNineConstants';

export type TopNineSoundResult = 'played' | 'cooldown' | 'muted' | 'silent';

let lastChimeAt: number | null = null;

/** A switch worth hearing. Returns what happened, for tests; only a played chime starts the cooldown. */
export function chimeTopNine(enabled: boolean, now: number = Date.now()): TopNineSoundResult {
  if (!enabled || !deskSoundAudible('topNine')) return 'muted';
  if (lastChimeAt != null && now - lastChimeAt < TOP_NINE_CHIME_COOLDOWN_MS) return 'cooldown';
  if (!playDeskTone('topNine', DESK_TONE_TOP_NINE_CHIME)) return 'silent';
  lastChimeAt = now;
  return 'played';
}

/** A stock on screen halted. */
export function beepTopNineHalt(enabled: boolean): TopNineSoundResult {
  if (!enabled || !deskSoundAudible('topNine')) return 'muted';
  return playDeskTone('topNine', DESK_TONE_TOP_NINE_HALT) ? 'played' : 'silent';
}

/** Test-only: forget the last chime. */
export function resetTopNineSoundForTests(): void {
  lastChimeAt = null;
}
