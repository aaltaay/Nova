/**
 * Settings (frozen mockup R2-More): where the desk is trading, the two locks, the Level 2 marks, and how
 * good the link to the PC is. The venue and the padlock are the desk's own; this screen only shows them
 * and asks the desk to change what the phone's door allows: the venue (the desk's own switch), the
 * padlock on Paper and Sim, and this phone's lock (ADR 070 amendment 2026-11-13).
 */
import { useEffect, useState } from 'react';
import { Lock, LockOpen, Smartphone } from 'lucide-react';
import { LINK_LIMIT_MS } from '../../phone_link';
import { BackButton, LinkPill, PhoneScreen } from '../PhoneChrome';
import { PIN_NOT_SET } from '../PhonePinSheet';
import { usePhoneSession, type Venue } from '../PhoneSession';
import { setLevel2Marks, useLevel2Marks } from '../trade/level2MarksSwitch';
import { lastLevel2Age } from '../trade/usePhoneTrade';
import './settings.css';

const VENUES: readonly { id: Venue; name: string; note: string }[] = [
  { id: 'live', name: 'LIVE', note: 'real money' },
  { id: 'paper', name: 'PAPER', note: 'live prices' },
  { id: 'sim', name: 'SIM', note: "desk's replay" },
];
const NOT_BUILT = 'Not built yet. It will arrive switched off, and stay off until you turn it on.';
const HELP: readonly { name: string; note: string }[] = [
  { name: 'Stop with every Live buy', note: 'Held at IBKR · works if the PC goes down' },
  { name: 'Stop if this phone goes silent', note: 'Paper and Sim · off: the desk only alarms' },
];

function timeLeft(expiresAt: number | null, nowSec: number): string {
  if (expiresAt == null) return '';
  const min = Math.max(0, Math.floor((expiresAt - nowSec) / 60));
  return min >= 60 ? `${Math.floor(min / 60)} h ${min % 60} min left` : `${min} min left`;
}

export function SettingsScreen() {
  const s = usePhoneSession();
  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNowMs(Date.now()), 20_000);
    return () => window.clearInterval(timer);
  }, []);
  // The session ends on the PC's clock: read it there.
  const pcNowSec = (nowMs + (s.link.offsetMs ?? 0)) / 1000;
  const rt = s.link.roundTrip;
  const reachable = s.link.reachable !== false;
  const book = lastLevel2Age();
  const marksOn = useLevel2Marks();
  const padlockWords = s.armed == null
    ? 'Waiting for the desk'
    : s.armed
      ? `${s.venue ? s.venue[0].toUpperCase() + s.venue.slice(1) : 'The desk'}'s orders can go · same as the desk`
      : 'Nothing is sent while it is locked';
  const padlockWhy = s.armed == null
    ? 'Waiting for the desk to say whether the padlock is open.'
    : !s.armed && s.trades === false
      ? 'From the phone, Live is look only: the padlock opens on Paper and Sim. Lock still works on any venue.'
      : undefined;

  return (
    <PhoneScreen
      name="settings"
      tab={null}
      header={(
        <div className="ph-head has-back ph-set__head">
          <BackButton to={{ screen: 'home' }} label="Back" />
          <div className="ph-head__title">Settings</div>
          <div className="ph-grow" />
          <LinkPill words="Connected to your PC" />
        </div>
      )}
    >
      <div className="ph-set">
        <section>
          <div className="ph-label ph-set__label">Venue</div>
          <div className="ph-set__venues" data-testid="phone-settings-venues">
            {VENUES.map((v) => {
              const here = v.id === s.venue;
              return (
                <button
                  key={v.id}
                  type="button"
                  data-venue={v.id}
                  aria-pressed={here}
                  data-testid={`phone-settings-venue-${v.id}`}
                  onClick={() => {
                    if (!here) s.moveVenue(v.id);
                  }}
                >
                  <b>{v.name}</b>
                  <span>{here ? 'you are here' : v.note}</span>
                </button>
              );
            })}
          </div>
          <div className="ph-set__note">A tap switches the desk too. From the phone, Live is look only.</div>
        </section>

        <section>
          <div className="ph-label ph-set__label">Locks</div>
          <div className="ph-card ph-set__rows">
            <div className="ph-set__row" data-testid="phone-settings-padlock">
              <span className="ph-set__icon" data-state={s.armed ? 'open' : 'locked'}>
                {s.armed ? <LockOpen size={16} aria-hidden="true" /> : <Lock size={16} aria-hidden="true" />}
              </span>
              <span className="ph-set__words">
                <b>{s.armed == null ? 'Padlock' : s.armed ? 'Padlock open' : 'Padlock locked'}</b>
                <i>{padlockWords}</i>
              </span>
              <button
                type="button"
                className="ph-pill-btn ph-set__btn"
                disabled={Boolean(padlockWhy)}
                data-why={padlockWhy}
                onClick={() => s.setArmed(!s.armed)}
              >
                {s.armed ? 'Lock' : 'Unlock'}
              </button>
            </div>
            <div className="ph-set__row" data-testid="phone-settings-phone">
              <span className="ph-set__icon" data-state={s.unlocked ? 'open' : 'locked'}>
                <Smartphone size={16} aria-hidden="true" />
              </span>
              <span className="ph-set__words">
                <b>{s.unlocked ? 'This phone is unlocked' : 'This phone is locked'}</b>
                <i>
                  {s.unlocked
                    ? `${timeLeft(s.expiresAt, pcNowSec)} · ends if Nova restarts`
                    : s.pinSet === false ? 'No PIN is set on the PC yet' : 'The PIN you use on your PC opens it for 8 hours'}
                </i>
              </span>
              {s.unlocked ? (
                <button type="button" className="ph-pill-btn ph-set__btn" onClick={s.lockPhone}>Lock</button>
              ) : (
                <button
                  type="button"
                  className="ph-pill-btn ph-set__btn"
                  disabled={s.pinSet === false}
                  data-why={s.pinSet === false ? PIN_NOT_SET : undefined}
                  onClick={() => s.askPin()}
                >
                  Unlock
                </button>
              )}
            </div>
          </div>
        </section>

        <section>
          <div className="ph-label ph-set__label">Level 2</div>
          <div className="ph-card ph-set__rows">
            <div className="ph-set__row" data-testid="phone-settings-marks">
              <span className="ph-set__words">
                <b>The desk's marks on the book</b>
                <i>Big orders, hidden size, pulls · the depth chart</i>
              </span>
              <button
                type="button"
                className="ph-set__switch"
                role="switch"
                aria-checked={marksOn}
                aria-label={`The desk's Level 2 marks: ${marksOn ? 'on' : 'off'}`}
                onClick={() => setLevel2Marks(!marksOn)}
              >
                <span><i /></span>
              </button>
              <span className="ph-set__off">{marksOn ? 'On' : 'Off'}</span>
            </div>
          </div>
        </section>

        <section>
          <div className="ph-label ph-set__label"><span>Automatic help</span><span className="ph-faint">Off until you turn it on</span></div>
          <div className="ph-card ph-set__rows">
            {HELP.map((h) => (
              <div key={h.name} className="ph-set__row">
                <span className="ph-set__words">
                  <b>{h.name}</b>
                  <i>{h.note}</i>
                </span>
                <button type="button" className="ph-set__switch" role="switch" aria-checked="false" aria-label={`${h.name}: off`} disabled data-why={NOT_BUILT}>
                  <span><i /></span>
                </button>
                <span className="ph-set__off">Off</span>
              </div>
            ))}
          </div>
        </section>

        <section>
          <div className="ph-label ph-set__label"><span>Link to your PC</span><span className="ph-faint">Last 30 s</span></div>
          <div className="ph-card ph-set__link" data-testid="phone-settings-link">
            <div>
              <i>Tap</i>
              <b className={!reachable ? 'ph-bad' : rt ? (rt.p50 <= LINK_LIMIT_MS ? 'ph-good' : 'ph-warn') : ''}>
                {!reachable ? 'No link' : rt ? `${Math.round(rt.p50)} ms` : '…'}
              </b>
            </div>
            <div>
              <i>Slowest</i>
              <b className={rt ? (rt.max <= LINK_LIMIT_MS ? 'ph-good' : 'ph-warn') : ''}>{rt ? `${Math.round(rt.max)} ms` : '…'}</b>
            </div>
            <div>
              <i>Drops</i>
              <b className={s.link.drops ? 'ph-warn' : ''}>{s.link.drops}</b>
            </div>
            <div data-testid="phone-settings-level2">
              <i>Level 2</i>
              <b className={book ? (book.ms <= LINK_LIMIT_MS ? 'ph-good' : 'ph-warn') : 'ph-faint'}>
                {book ? (book.ms < 1_000 ? `${Math.round(book.ms)} ms` : `${(book.ms / 1_000).toFixed(1)} s`) : '—'}
              </b>
            </div>
          </div>
          <div className="ph-set__note">
            Limit {LINK_LIMIT_MS} ms. Over it, new buys are held. Level 2 is {book ? `${book.symbol}'s book, as last seen on Trade` : 'measured once Trade opens a book'}.
          </div>
        </section>
      </div>
    </PhoneScreen>
  );
}
