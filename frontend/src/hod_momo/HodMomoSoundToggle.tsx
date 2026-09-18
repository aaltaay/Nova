/**
 * Small speaker on/off for the HOD Momo new-row ping.
 * Desk mute only -- not StrategyConfig.audio.
 */
import { Volume2, VolumeX } from 'lucide-react';
import { useEffect, useState } from 'react';
import {
  isHodMomoAlertSoundOn,
  setHodMomoAlertSoundOn,
  subscribeHodMomoAlertSound,
  unlockHodMomoAlertAudio,
} from './hodMomoAlertSound';

type Props = {
  className?: string;
};

export function HodMomoSoundToggle({ className }: Props) {
  const [on, setOn] = useState(isHodMomoAlertSoundOn);

  useEffect(() => subscribeHodMomoAlertSound(setOn), []);

  return (
    <button
      type="button"
      className={className}
      aria-pressed={on}
      aria-label={on ? 'HOD alert sound on' : 'HOD alert sound off'}
      title={on ? 'Mute HOD new-row ping' : 'Unmute HOD new-row ping'}
      data-testid="hod-momo-sound-toggle"
      onClick={() => {
        const next = !on;
        setHodMomoAlertSoundOn(next);
        unlockHodMomoAlertAudio();
      }}
    >
      {on ? (
        <Volume2 size={14} strokeWidth={2} aria-hidden="true" />
      ) : (
        <VolumeX size={14} strokeWidth={2} aria-hidden="true" />
      )}
    </button>
  );
}
