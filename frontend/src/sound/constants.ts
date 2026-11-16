/** The header mute and the desk's voice (desk-ops.md, "The desk's voice and the header mute"). */

/** `prefStore` envelope `{schema_version: 1, value: boolean}`, shared by every window. */
export const DESK_SOUND_MUTED_KEY = 'nova.desk.sound.muted';
/** Sound is on until the operator mutes it (they asked for the voice). */
export const DESK_SOUND_MUTED_DEFAULT = false;

/** A touch quicker than the default: a fill is news only while it is fresh. */
export const DESK_VOICE_RATE = 1.1;
/** Sentences waiting to be said before the oldest are dropped for the newest. */
export const DESK_VOICE_MAX_QUEUED = 4;

export const DESK_MUTE_ARIA_ON = 'Sound on';
export const DESK_MUTE_ARIA_MUTED = 'Sound muted';
export const DESK_MUTE_TITLE_ON =
  'Sound on. Left click for the sound menu. Right click to mute every Nova sound.';
export const DESK_MUTE_TITLE_MUTED =
  'Muted: every Nova sound is off. Left click for the sound menu. Right click to turn sound back on.';
/** Said once when sound comes back on, so the operator hears that the voice works. */
export const DESK_SOUND_ON_SPOKEN = 'Sound on.';
/** Each source's own switch, while the header mute is on. */
export const DESK_MUTE_REASON = 'The header mute is on: every Nova sound is off.';

/** Each sound's row in the sound menu (desk-ops.md, "The sound menu"). */
export type DeskSoundId = 'hod' | 'setups' | 'topNine' | 'voice' | 'calls' | 'alarm' | 'stream';
export const DESK_SOUND_IDS: readonly DeskSoundId[] = ['hod', 'setups', 'topNine', 'voice', 'calls', 'alarm', 'stream'];

/** Where each switch has always been kept; the stream's is never stored. */
export const DESK_SOUND_KEYS = {
  hod: 'nova.hodMomo.alertSound.enabled',
  setups: 'nova.setups.sound.v1',
  topNine: 'nova.topNine.sound',
  voice: 'nova.desk.voice.on',
  calls: 'nova.stockRead.sound',
  alarm: 'nova_os_attention_muted',
} as const;

/** `prefStore` envelope `{schema_version: 1, value: {[id]: 0-100}}`, shared by every window. */
export const DESK_SOUND_LEVELS_KEY = 'nova.desk.sound.levels';
export const DESK_SOUND_LEVEL_MAX = 100;
/** The level each sound has always played at, as a share of the desk's loudest (0.22): an untouched desk sounds as it did. */
export const DESK_SOUND_LEVEL_DEFAULTS: Readonly<Record<DeskSoundId, number>> = {
  hod: 18,
  setups: 23,
  topNine: 91,
  voice: 100,
  calls: 27,
  alarm: 18,
  stream: 50,
};

export interface DeskTone {
  hz: readonly number[];
  noteSec: number;
  gapSec: number;
  /** The peak at the sound's default level. */
  gain: number;
}

export const DESK_TONE_HOD: DeskTone = { hz: [880], noteSec: 0.18, gapSec: 0, gain: 0.04 };
export const DESK_TONE_SETUPS: DeskTone = { hz: [1_175], noteSec: 0.22, gapSec: 0, gain: 0.05 };
/** Two rising notes, loud enough to hear over the desk (the old 0.05 tick was not). */
export const DESK_TONE_TOP_NINE_CHIME: DeskTone = { hz: [880, 1_320], noteSec: 0.12, gapSec: 0, gain: 0.2 };
/** A stock on screen halted: three short lower beeps, unlike the chime. */
export const DESK_TONE_TOP_NINE_HALT: DeskTone = { hz: [740, 740, 740], noteSec: 0.09, gapSec: 0.07, gain: 0.22 };
/** A call to act; the Trader's other calls change only the notes. */
export const DESK_TONE_CALL: DeskTone = { hz: [880, 1_175], noteSec: 0.11, gapSec: 0.03, gain: 0.06 };
/** One low tone: every remaining attention kind (kill, risk halt, archive failure) is a warning. */
export const DESK_TONE_ALARM: DeskTone = { hz: [220], noteSec: 0.18, gapSec: 0, gain: 0.04 };

/** What the menu's Play says for the voice. */
export const DESK_VOICE_SAMPLE = 'Bought 100 shares of A B C.';

export const DESK_SOUND_ALL_LABEL = 'All sounds';
export const DESK_SOUND_SECTIONS: readonly { title: string; tile: string; rows: readonly { id: DeskSoundId; label: string }[] }[] = [
  { title: 'Scanner', tile: 'scanner', rows: [{ id: 'hod', label: 'HOD alerts' }, { id: 'setups', label: 'Setups' }] },
  { title: 'Nine charts', tile: 'charts', rows: [{ id: 'topNine', label: 'Moved up' }] },
  {
    title: 'Trades',
    tile: 'trades',
    rows: [{ id: 'voice', label: 'Fill voice' }, { id: 'calls', label: 'Trader calls' }, { id: 'alarm', label: 'Alarm' }],
  },
  { title: 'YouTube', tile: 'youtube', rows: [{ id: 'stream', label: 'TraderTV' }] },
];
export const DESK_SOUND_TIPS: Partial<Record<DeskSoundId, string>> = {
  hod: 'A ping for each new HOD Momo alert.',
  setups: 'A ping when the bot raises a proposal.',
  topNine: 'A chime when a chart in the Top 9 window moves up, and three beeps when one halts. It plays while that window is open.',
  voice: 'Says each fill. It also says the loss-limit warnings and "Order rejected."',
  calls: 'A ping for ENTER NOW, SELL NOW and what Nova just did.',
  alarm: 'A low tone for a kill, a risk halt or an archive failure.',
};
export const DESK_SOUND_LEVEL_ZERO = 'Its volume is 0.';
export const DESK_STREAM_LIVE = 'Live';
export const DESK_STREAM_OFF_AIR = 'The stream is off air.';
export const DESK_STREAM_NOT_OPEN = 'Open the stream on the LiveTrader Bots page first.';

export const DESK_VOICE_PROBLEM_PREFIX = 'The voice cannot speak in this window:';
export const DESK_VOICE_NO_SPEECH = 'this browser has no speech.';
export const DESK_VOICE_NOT_ALLOWED = 'the browser holds speech until you click in this window once.';
export const DESK_VOICE_FAILED = 'the computer refused to speak';
