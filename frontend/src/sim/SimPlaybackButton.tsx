import { Pause, Play } from 'lucide-react';
import type { SimClockState } from './simClockTypes';
import { simWhyPlayback } from './simConstants';
import { useReplayActions } from './useReplayActions';
import { simClockWhy } from './simWhy';
export function SimPlaybackButton({ clock, onClock, onBeforeChange, onSettled, symbol }: {
  clock: SimClockState | null; onClock: (clock: SimClockState) => void;
  onBeforeChange?: () => void; onSettled?: () => void;
  /** The tab the operator is looking at: a pause off the live edge loads its Session Record for today. */
  symbol?: string | null;
}) {
  const { request, busy, errors } = useReplayActions();
  const paused = clock?.paused === true;
  const label = paused ? 'Play Sim time' : 'Pause Sim time';
  const why = simClockWhy(clock) ?? (busy.has('playback') ? simWhyPlayback(paused) : null);
  const toggle = async () => {
    onBeforeChange?.();
    const body = symbol ? { paused: !paused, symbol } : { paused: !paused };
    const next = await request<SimClockState>('playback', '/clock', body, 'Could not change Sim playback. Try again.');
    if (next) onClock(next);
    onSettled?.();
  };
  // Locked, the title is '' so neither it nor the Trader strip's own title shows over the reason.
  return <>
    <button type="button" aria-label={label} title={why ? '' : label} disabled={busy.has('playback') || !clock?.sim}
      data-why={why ?? undefined} onClick={() => void toggle()}>
      {paused ? <Play size={14} aria-hidden="true" /> : <Pause size={14} aria-hidden="true" />}
    </button>
    {errors.playback && <span role="alert" className="sim-error">{errors.playback}</span>}
  </>;
}
