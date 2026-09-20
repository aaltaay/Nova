import { Pause, Play } from 'lucide-react';
import type { SimClockState } from './simClockTypes';
import { useReplayActions } from './useReplayActions';
export function SimPlaybackButton({ clock, onClock, onBeforeChange, onSettled }: {
  clock: SimClockState | null; onClock: (clock: SimClockState) => void;
  onBeforeChange?: () => void; onSettled?: () => void;
}) {
  const { request, busy, errors } = useReplayActions();
  const paused = clock?.paused === true;
  const label = paused ? 'Play Sim time' : 'Pause Sim time';
  const toggle = async () => {
    onBeforeChange?.();
    const next = await request<SimClockState>('playback', '/clock', { paused: !paused }, 'Could not change Sim playback. Try again.');
    if (next) onClock(next);
    onSettled?.();
  };
  return <>
    <button type="button" aria-label={label} title={label} disabled={busy.has('playback') || !clock?.sim} onClick={() => void toggle()}>
      {paused ? <Play size={14} aria-hidden="true" /> : <Pause size={14} aria-hidden="true" />}
    </button>
    {errors.playback && <span role="alert" className="sim-error">{errors.playback}</span>}
  </>;
}
