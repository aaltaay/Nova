import { useState } from 'react';
import { Pause, Play } from 'lucide-react';
import { API_BASE_URL } from '../constants';
import { novaFetch } from '../api/novaFetch';
import type { SimClockState } from './simClockTypes';

export function SimPlaybackButton({ clock, onClock }: {
  clock: SimClockState | null;
  onClock: (clock: SimClockState) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const paused = clock?.paused === true;
  const label = paused ? 'Play Sim time' : 'Pause Sim time';
  const toggle = async () => {
    setBusy(true);
    setError('');
    try {
      const response = await novaFetch(`${API_BASE_URL}/api/sim/clock`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ paused: !paused }),
      });
      if (!response.ok) throw new Error('Could not change Sim playback. Try again.');
      onClock(await response.json() as SimClockState);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not change Sim playback.');
    } finally {
      setBusy(false);
    }
  };
  return <>
    <button type="button" aria-label={label} title={label}
      disabled={busy || !clock?.sim} onClick={() => void toggle()}>
      {paused ? <Play size={14} aria-hidden="true" /> : <Pause size={14} aria-hidden="true" />}
    </button>
    {error && <span role="alert">{error}</span>}
  </>;
}
