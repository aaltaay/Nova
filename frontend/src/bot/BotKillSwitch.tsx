/**
 * The kill switch on the Bots page hero (D-037, ADR 025, ADR 042 D): it cancels every
 * working order on every venue and refuses every new order on every venue (a sell included; Flatten
 * and cancels still work) until you reset it;
 * it does not sell positions. After a trip the page says what the sweep did on each
 * venue -- cancelled, still working, or not read at all (a Gateway that is down is a
 * stated failure, never "nothing to cancel").
 */
import { KILL_SWITCH_HINT, KILL_SWITCH_TITLE } from '../constantGroups/bot';
import {
  BOTS_KILL_BUSY_WHY,
  BOTS_KILL_RESET_LABEL,
  BOTS_KILL_SWEEP_HEAD,
  BOTS_KILL_SWEEP_NOTHING,
  BOTS_KILL_TRIP_NOTE,
  BOTS_KILL_TRIPPED_NOTE,
  BOTS_KILL_UNREAD_WHY,
  BOTS_VENUE_NAMES,
  botsKillSweepCancelled,
  botsKillSweepFailed,
} from '../constantGroups/bots_page';
import { tipProps } from '../ux/hoverTip';
import { prose } from './botsPageFormat';
import type { KillSweep } from './killSwitchApi';
import type { KillSwitchControl } from './useKillSwitch';

const ids = (list: number[]) => list.map(id => `#${id}`).join(', ');

/** One venue's sweep in words: what it cancelled, what still works, or why it could not read. */
export function sweepWords(s: KillSweep): string {
  const venue = BOTS_VENUE_NAMES[s.venue] ?? s.venue;
  const parts: string[] = [];
  if (s.cancelled.length) parts.push(botsKillSweepCancelled(s.cancelled.length, ids(s.cancelled)));
  if (s.failed.length) parts.push(botsKillSweepFailed(s.failed.length, ids(s.failed)));
  if (s.error) parts.push(prose(s.error));
  if (!parts.length) parts.push(BOTS_KILL_SWEEP_NOTHING);
  return `${venue}: ${parts.join(' · ')}`;
}

export function BotKillSwitch({ killSwitch }: { killSwitch: KillSwitchControl }) {
  const tripped = killSwitch.status?.tripped === true;
  const sweep = killSwitch.sweep;
  return (
    <>
      {tripped ? (
        <>
          <p className="bots-hero__killed" role="status">{BOTS_KILL_TRIPPED_NOTE}</p>
          <button type="button" className="bots-btn bots-btn--block" data-testid="bots-kill-reset"
            disabled={killSwitch.busy} data-why={killSwitch.busy ? BOTS_KILL_BUSY_WHY : undefined}
            onClick={() => void killSwitch.act(false)}>
            {BOTS_KILL_RESET_LABEL}
          </button>
        </>
      ) : (
        <button type="button" className="bots-btn bots-btn--danger bots-btn--block bots-kill" data-testid="bots-kill-trip"
          disabled={killSwitch.busy || killSwitch.status == null}
          data-why={killSwitch.busy ? BOTS_KILL_BUSY_WHY
            : killSwitch.status == null ? BOTS_KILL_UNREAD_WHY(killSwitch.error ?? null) : undefined}
          {...tipProps(KILL_SWITCH_HINT, KILL_SWITCH_TITLE)}
          onClick={() => void killSwitch.act(true)}>
          ■ {KILL_SWITCH_TITLE}
          <small>{BOTS_KILL_TRIP_NOTE}</small>
        </button>
      )}
      {sweep ? (
        <div className="bots-hero__sweep" role="status" data-testid="bots-kill-sweep">
          <b>{BOTS_KILL_SWEEP_HEAD}</b>
          {sweep.length === 0 ? <span>{BOTS_KILL_SWEEP_NOTHING}</span> : null}
          {sweep.map(s => (
            <span key={s.venue} className={s.error || s.failed.length ? 'is-bad' : ''} data-testid={`bots-kill-sweep-${s.venue}`}>
              {sweepWords(s)}
            </span>
          ))}
        </div>
      ) : null}
      {killSwitch.error ? <p className="bots-hero__error" data-testid="bots-kill-error">{killSwitch.error}</p> : null}
    </>
  );
}
