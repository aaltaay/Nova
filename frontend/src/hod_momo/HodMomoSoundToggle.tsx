import { useState } from 'react';
import {
  hydrateHodMomoAlertSoundFromStorage,
  setHodMomoAlertSoundOn,
} from './hodMomoAlertPing';

function SpeakerIcon({ on }: { on: boolean }) {
  return (
    <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true">
      <path fill="currentColor" d="M2.2 6.2h2.4L8 3.6v8.8L4.6 9.8H2.2V6.2z" />
      {on ? (
        <path
          fill="none"
          stroke="currentColor"
          strokeWidth="1.3"
          d="M10.4 5.4a3.2 3.2 0 0 1 0 5.2"
        />
      ) : (
        <path
          fill="none"
          stroke="currentColor"
          strokeWidth="1.3"
          d="M10.6 5.2 14 10.8M14 5.2 10.6 10.8"
        />
      )}
    </svg>
  );
}

/** Banner mute for the HOD new-row ping. Visible without opening Configure. */
export function HodMomoSoundToggle() {
  const [on, setOn] = useState(() => hydrateHodMomoAlertSoundFromStorage());

  function toggle() {
    const next = !on;
    setHodMomoAlertSoundOn(next);
    setOn(next);
  }

  return (
    <button
      type="button"
      className={`hod-sound-btn${on ? ' is-on' : ' is-off'}`}
      onClick={toggle}
      aria-pressed={on}
      aria-label={on ? 'HOD alert sound on' : 'HOD alert sound off'}
      title={on ? 'Mute HOD alert ping' : 'Unmute HOD alert ping'}
      data-testid="hod-momo-sound-toggle"
    >
      <SpeakerIcon on={on} />
    </button>
  );
}
