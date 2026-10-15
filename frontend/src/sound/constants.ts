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
  'Sound on: Nova says each fill out loud, and alerts ping. Click to mute every Nova sound.';
export const DESK_MUTE_TITLE_MUTED =
  'Muted: every Nova sound is off -- the voice, the pings and alarms, the stream. Click to turn sound back on.';
/** Said once when sound comes back on, so the operator hears that the voice works. */
export const DESK_SOUND_ON_SPOKEN = 'Sound on.';
/** Each source's own switch, while the header mute is on. */
export const DESK_MUTE_REASON = 'The header mute is on: every Nova sound is off.';

export const DESK_VOICE_PROBLEM_PREFIX = 'The voice cannot speak in this window:';
export const DESK_VOICE_NO_SPEECH = 'this browser has no speech.';
export const DESK_VOICE_NOT_ALLOWED = 'the browser holds speech until you click in this window once.';
export const DESK_VOICE_FAILED = 'the computer refused to speak';
