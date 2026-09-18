import { useEffect, useState } from 'react';
import {
  isHodMomoAlertSoundEnabled,
  setHodMomoAlertSoundEnabled,
  subscribeHodMomoAlertSound,
} from './hodMomoAlertSound';

type Props = {
  className?: string;
};

export function HodMomoSoundToggle({ className = '' }: Props) {
  const [on, setOn] = useState(isHodMomoAlertSoundEnabled);

  useEffect(() => subscribeHodMomoAlertSound(setOn), []);

  const title = on ? 'Mute HOD alert ping' : 'Unmute HOD alert ping';
  return (
    <button
      type="button"
      className={`hod-sound-btn${on ? '' : ' hod-sound-btn--off'}${className ? ` ${className}` : ''}`}
      aria-pressed={on}
      aria-label={on ? 'HOD alert sound on' : 'HOD alert sound off'}
      title={title}
      data-testid="hod-momo-sound-toggle"
      onClick={() => setHodMomoAlertSoundEnabled(!on)}
    >
      <span className="hod-sound-btn__icon" aria-hidden="true">
        {on ? (
          <svg viewBox="0 0 16 16" width="14" height="14">
            <path
              fill="currentColor"
              d="M2.5 6.2h2.1L7.8 3.6v8.8L4.6 9.8H2.5A.8.8 0 0 1 1.7 9V7a.8.8 0 0 1 .8-.8Zm8.2-.7a3.4 3.4 0 0 1 0 5m1.9-6.6a6 6 0 0 1 0 8.2"
              stroke="currentColor"
              strokeWidth="1.2"
              strokeLinecap="round"
              fillOpacity="0.15"
            />
          </svg>
        ) : (
          <svg viewBox="0 0 16 16" width="14" height="14">
            <path
              fill="currentColor"
              d="M2.5 6.2h2.1L7.8 3.6v8.8L4.6 9.8H2.5A.8.8 0 0 1 1.7 9V7a.8.8 0 0 1 .8-.8Z"
              fillOpacity="0.35"
            />
            <path
              d="M10.2 6.2 14 10m0-3.8-3.8 3.8"
              stroke="currentColor"
              strokeWidth="1.3"
              strokeLinecap="round"
            />
          </svg>
        )}
      </span>
    </button>
  );
}
