/** Feature-local tunables for the HOD Momo new-row ping. */

/** localStorage: banner speaker on/off. Default on. */
export const HOD_MOMO_ALERT_SOUND_KEY = 'nova.hodMomo.alertSound.enabled';
export const HOD_MOMO_ALERT_SOUND_DEFAULT = true;

/** One ping covers every new HOD row that lands inside this window. */
export const HOD_MOMO_ALERT_SOUND_COALESCE_MS = 400;

/** Same quiet Web Audio oscillator family as the attention strip cue. */
export const HOD_MOMO_ALERT_PING_HZ = 880;
export const HOD_MOMO_ALERT_PING_GAIN = 0.04;
export const HOD_MOMO_ALERT_PING_SEC = 0.18;
