/**
 * The strip under the Trade header on a venue the phone does not simply trade live (ADR 070 amendment
 * 2026-11-13, mockup v3): on Sim, the desk's playhead -- its time and day, a minute back, play or pause, a
 * minute on -- moved through the desk's own clock, so the PC's replay moves with it; on Live, the reminder
 * that the phone only looks.
 *
 * The strip holds no clock of its own: it reads the shared Sim clock poll (`simClockResource`) and every
 * button asks the desk, whose answer the poll takes in at once.
 */
import { Pause, Play, StepBack, StepForward } from 'lucide-react';
import { SIM_STRIP_STEP_MINUTES } from '../../constants';
import { formatClock, formatShortDate, type SimClockState } from '../../sim';
import { usePhoneSession } from '../PhoneSession';
import './simStrip.css';

/** What the strip calls the playhead: the live edge, paused, or playing a replay. */
export function simStripState(clock: SimClockState | null): string {
  if (!clock) return 'reading the desk';
  if (clock.live_edge) return 'live edge';
  if (clock.paused) return 'paused';
  return clock.replay_source === 'capture' || clock.replay_source === 'historical' ? 'replay' : 'nothing loaded';
}

export function SimStrip({ symbol, clock }: { symbol: string; clock: SimClockState | null }) {
  const { moveSim } = usePhoneSession();
  const why = !clock ? "Waiting for the desk's Sim clock." : clock.sim ? null : 'The desk is not on Sim.';
  const minute = clock?.minute_from_open ?? 0;
  const last = clock?.minute_max ?? null;
  const paused = clock?.paused === true;
  const step = (by: number): void => {
    const to = Math.max(0, Math.round(minute + by));
    moveSim(by < 0 ? 'Back a minute' : 'On a minute', { minute_from_open: last != null ? Math.min(last, to) : to, symbol });
  };
  return (
    <div className="ph-simstrip" data-testid="phone-sim-strip" role="group" aria-label="The desk's Sim playhead">
      <button type="button" aria-label={`Back ${SIM_STRIP_STEP_MINUTES} minute`} disabled={Boolean(why)} data-why={why ?? undefined} onClick={() => step(-SIM_STRIP_STEP_MINUTES)}>
        <StepBack size={13} aria-hidden="true" />
      </button>
      <button
        type="button"
        aria-label={paused ? 'Play Sim time' : 'Pause Sim time'}
        disabled={Boolean(why)}
        data-why={why ?? undefined}
        data-testid="phone-sim-play"
        onClick={() => moveSim(paused ? 'Play' : 'Pause', { paused: !paused, symbol })}
      >
        {paused ? <Play size={13} aria-hidden="true" /> : <Pause size={13} aria-hidden="true" />}
      </button>
      <button type="button" aria-label={`On ${SIM_STRIP_STEP_MINUTES} minute`} disabled={Boolean(why)} data-why={why ?? undefined} onClick={() => step(SIM_STRIP_STEP_MINUTES)}>
        <StepForward size={13} aria-hidden="true" />
      </button>
      <b>{formatClock(clock?.sim_time_et)}</b>
      <span>{formatShortDate(clock?.session_date ?? null)}</span>
      <span className="ph-grow" />
      <i>{simStripState(clock)}</i>
    </div>
  );
}

/** On Live the phone looks and never sends: said once, over the chart. */
export function LiveBand() {
  return (
    <div className="ph-liveband" role="status" data-testid="phone-live-band">
      LIVE · real money <span>· look only from the phone</span>
    </div>
  );
}
