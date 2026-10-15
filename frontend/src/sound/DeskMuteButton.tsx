/** The header's mute: a speaker left of the padlock. One click silences every Nova sound; another brings it back. */
import { useSyncExternalStore } from 'react';
import { Volume2, VolumeX } from 'lucide-react';
import {
  DESK_MUTE_ARIA_MUTED,
  DESK_MUTE_ARIA_ON,
  DESK_MUTE_TITLE_MUTED,
  DESK_MUTE_TITLE_ON,
  DESK_SOUND_ON_SPOKEN,
  DESK_VOICE_PROBLEM_PREFIX,
} from './constants';
import { setDeskMuted, useDeskMuted } from './deskMute';
import { deskVoiceProblem, speakDesk, subscribeDeskVoiceProblem } from './speech';

export function DeskMuteButton() {
  const muted = useDeskMuted();
  const problem = useSyncExternalStore(subscribeDeskVoiceProblem, deskVoiceProblem);
  const title = muted
    ? DESK_MUTE_TITLE_MUTED
    : problem ? `${DESK_MUTE_TITLE_ON}\n${DESK_VOICE_PROBLEM_PREFIX} ${problem}` : DESK_MUTE_TITLE_ON;

  function onClick() {
    const next = !muted;
    setDeskMuted(next);
    // Back on: say so, which proves the speaker works (and the click lets the browser speak).
    if (!next) speakDesk(DESK_SOUND_ON_SPOKEN);
  }

  return (
    <button
      type="button"
      className={`global-app-bar__icon-btn global-app-bar__mute${muted ? ' is-muted' : ''}${problem && !muted ? ' has-problem' : ''}`}
      title={title}
      aria-label={muted ? DESK_MUTE_ARIA_MUTED : DESK_MUTE_ARIA_ON}
      aria-pressed={muted}
      data-testid="global-bar-mute"
      data-muted={muted}
      onClick={onClick}
    >
      {muted
        ? <VolumeX className="global-app-bar__icon" aria-hidden />
        : <Volume2 className="global-app-bar__icon" aria-hidden />}
    </button>
  );
}
