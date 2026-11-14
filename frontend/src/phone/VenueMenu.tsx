/**
 * The venue menu (ADR 070 amendment 2026-11-13, mockup v3): the venue pill on every screen opens three rows,
 * and a tap on a row switches the desk at once, as the pill in the PC's header does. One venue for both.
 *
 * Before the tap the menu says what the switch would cancel or turn off, in the desk's words
 * (`/api/phone/venue/effects`): amber when something would go, a quiet line when nothing would. A check Nova
 * could not read is named, never read as nothing. The switch itself is the desk's (`/api/venue` through the
 * phone's door); the banner says it switched only on the desk's answer.
 */
import { useEffect, useState } from 'react';
import { Check } from 'lucide-react';
import type { VenueEffects } from '../phone_link';
import { formatClock, formatShortDate, simClockResource, type SimClockState } from '../sim';
import { usePhoneSession, type Venue } from './PhoneSession';
import './venueMenu.css';

const NAME: Record<Venue, string> = { live: 'Live', paper: 'Paper', sim: 'Sim' };
const WORD: Record<Venue, string> = { live: 'LIVE', paper: 'PAPER', sim: 'SIM' };

/** What the Sim row says: what the desk has loaded, and where its playhead is. */
export function simRowNote(clock: SimClockState | null): string {
  if (!clock) return 'the desk\'s replay';
  if (clock.live_edge) return 'the live edge · live IBKR prices';
  const symbol = (clock.replay_symbol ?? '').trim().toUpperCase();
  const day = formatShortDate(clock.session_date ?? clock.replay_date ?? null);
  const at = clock.sim_time_et ? formatClock(clock.sim_time_et) : '';
  if (!symbol && clock.replay_source !== 'historical' && clock.replay_source !== 'capture') return `nothing loaded${day ? ` · ${day}` : ''}`;
  return [symbol, day, at].filter(Boolean).join(' · ');
}

const ROWS: readonly { id: Venue; title: string; note: (clock: SimClockState | null) => string }[] = [
  { id: 'paper', title: 'Practice money', note: () => 'live IBKR prices' },
  { id: 'sim', title: 'Replay', note: simRowNote },
  { id: 'live', title: 'Real money', note: () => 'IBKR · look only from the phone' },
];

/** The foot's words: what leaving `here` would change, or that nothing would. Null while it is read. */
export function effectsFoot(here: Venue, effects: VenueEffects | null | 'none'): { stake: boolean; text: string } | null {
  if (effects == null) return null;
  if (effects === 'none') return { stake: true, text: 'Nova did not say what the switch would change. Check the desk before you switch.' };
  const unread = effects.unknown.length ? ` Nova could not read: ${effects.unknown.join(', ')}.` : '';
  if (!effects.lines.length && !unread) return { stake: false, text: `Nothing working on ${NAME[here]}. Your own orders and shares stay on ${NAME[here]}.` };
  const lines = effects.lines.map((l) => (/[.!]$/.test(l) ? l : `${l}.`)).join(' ');
  return { stake: true, text: `${lines}${unread} Your own orders and shares stay on ${NAME[here]}.`.trim() };
}

export function VenueMenu({ side, onClose }: { side: 'left' | 'right'; onClose: () => void }) {
  const session = usePhoneSession();
  const here = session.venue;
  const [effects, setEffects] = useState<VenueEffects | null | 'none'>(null);
  const [clock, setClock] = useState<SimClockState | null>(() => simClockResource.getSnapshot().data);

  // Read what the switch would change each time the menu opens: what is working moves by the second.
  useEffect(() => {
    let live = true;
    void session.door.venueEffects().then((read) => {
      if (live) setEffects(read ?? 'none');
    });
    return () => {
      live = false;
    };
  }, [session.door]);
  // The Sim row names what the desk has loaded: the shared Sim clock, read while the menu is open.
  useEffect(() => simClockResource.subscribe(() => setClock(simClockResource.getSnapshot().data)), []);

  const foot = here ? effectsFoot(here, effects) : null;
  return (
    <>
      <button type="button" className="ph-vmenu__shade" aria-label="Close the venue menu" onClick={onClose} />
      <div className="ph-vmenu" data-side={side} role="menu" aria-label="Switch the desk's venue" data-testid="phone-venue-menu">
        {ROWS.map((row) => {
          const on = row.id === here;
          return (
            <button
              key={row.id}
              type="button"
              role="menuitemradio"
              aria-checked={on}
              className="ph-vmenu__row"
              data-venue={row.id}
              data-testid={`phone-venue-${row.id}`}
              onClick={() => {
                onClose();
                if (!on) session.moveVenue(row.id);
              }}
            >
              <span className="ph-vmenu__pill">{WORD[row.id]}</span>
              <span className="ph-vmenu__words"><b>{row.title}</b><span>{row.note(clock)}</span></span>
              {on ? <Check size={16} strokeWidth={3} aria-hidden="true" className="ph-vmenu__check" /> : null}
            </button>
          );
        })}
        {here == null ? (
          <div className="ph-vmenu__calm" role="status">Waiting for the desk to say where it is.</div>
        ) : foot == null ? (
          <div className="ph-vmenu__calm" role="status">Reading what a switch would change…</div>
        ) : foot.stake ? (
          <div className="ph-vmenu__stake" role="status" data-testid="phone-venue-stake"><b>Switching now:</b> {foot.text}</div>
        ) : (
          <div className="ph-vmenu__calm" role="status" data-testid="phone-venue-calm">{foot.text}</div>
        )}
      </div>
    </>
  );
}
