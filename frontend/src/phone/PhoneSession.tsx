/**
 * What every phone screen shares (ADR 070): the door to the desk (`/api/phone`), the heartbeat that
 * reads it, the banner that answers every tap, and the PIN sheet. The phone decides nothing here:
 * the venue, the padlock and every refusal are the desk's, shown as the desk words them.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from 'react';
import { API_BASE_URL } from '../constants';
import { PhoneDoor, type Answer } from '../phone_link';
import { createPhoneLink, type PhoneLinkView } from './phoneLink';
import { PhonePinSheet } from './PhonePinSheet';

export type BannerTone = 'sending' | 'done' | 'refused';

export interface PhoneBanner {
  tone: BannerTone;
  title: string;
  note: string;
}

export type Venue = 'live' | 'paper' | 'sim';

export interface PhoneSessionValue {
  door: PhoneDoor;
  link: PhoneLinkView;
  /** The desk's venue as the door last said it; null before the first answer. */
  venue: Venue | null;
  /** The desk's padlock: true when orders can go. Null before the first answer. */
  armed: boolean | null;
  /** This phone holds a session the backend still accepts. */
  unlocked: boolean;
  /** When that session ends, epoch seconds. */
  expiresAt: number | null;
  /** A phone PIN exists on the PC; null before the first answer. */
  pinSet: boolean | null;
  banner: PhoneBanner | null;
  dismissBanner: () => void;
  /** Open or close the desk's padlock. Asks for the PIN first when this phone is locked. */
  setArmed: (armed: boolean) => void;
  /** End this phone's session. */
  lockPhone: () => void;
  /** Ask for the PIN; `then` runs once the phone is unlocked. */
  askPin: (then?: () => void) => void;
  /** Send one write through the door, with a banner from tap to answer. Asks for the PIN first when locked. */
  send: (label: string, write: (door: PhoneDoor) => Promise<Answer>) => void;
}

const Ctx = createContext<PhoneSessionValue | null>(null);

/** How long a banner that says "done" stays. A refusal stays until it is tapped. */
const DONE_MS = 4_000;

function asVenue(value: unknown): Venue | null {
  return value === 'live' || value === 'paper' || value === 'sim' ? value : null;
}

export function PhoneSessionProvider({ children }: { children: ReactNode }) {
  const door = useMemo(() => new PhoneDoor(API_BASE_URL), []);
  const link = useMemo(() => createPhoneLink(door), [door]);
  const view = useSyncExternalStore(link.subscribe, link.get);
  const [banner, setBanner] = useState<PhoneBanner | null>(null);
  const [pinOpen, setPinOpen] = useState(false);
  const afterPin = useRef<(() => void) | null>(null);
  const doneTimer = useRef<number | null>(null);

  useEffect(() => {
    link.start();
    return () => link.stop();
  }, [link]);

  const show = useCallback((next: PhoneBanner | null) => {
    if (doneTimer.current != null) window.clearTimeout(doneTimer.current);
    doneTimer.current = null;
    setBanner(next);
    if (next?.tone === 'done') doneTimer.current = window.setTimeout(() => setBanner(null), DONE_MS);
  }, []);

  const status = view.status;
  const unlocked = status?.unlocked === true && door.hasSession();

  const askPin = useCallback((then?: () => void) => {
    afterPin.current = then ?? null;
    setPinOpen(true);
  }, []);

  const send = useCallback((label: string, write: (d: PhoneDoor) => Promise<Answer>) => {
    const run = (): void => {
      show({ tone: 'sending', title: `Sending · ${label}`, note: 'Waiting for the desk.' });
      void write(door).then((answer) => {
        link.refresh();
        if (answer.ok) {
          show({ tone: 'done', title: answer.text, note: `The desk answered in ${Math.round(answer.ms)} ms` });
        } else {
          show({ tone: 'refused', title: `NOT DONE · ${label}`, note: answer.text });
        }
      });
    };
    if (door.hasSession()) run();
    else askPin(run);
  }, [askPin, door, link, show]);

  const setArmed = useCallback((armed: boolean) => {
    send(armed ? 'Open the padlock' : 'Lock the padlock', (d) => d.arm(armed));
  }, [send]);

  const lockPhone = useCallback(() => {
    if (!door.hasSession()) return;
    show({ tone: 'sending', title: 'Locking this phone', note: 'Waiting for the desk.' });
    void door.lock().then((answer) => {
      link.refresh();
      show(answer.ok
        ? { tone: 'done', title: 'This phone is locked', note: 'Your PIN opens it again.' }
        : { tone: 'refused', title: 'NOT DONE · Lock this phone', note: answer.text });
    });
  }, [door, link, show]);

  const closePin = useCallback((ok: boolean) => {
    setPinOpen(false);
    const then = afterPin.current;
    afterPin.current = null;
    link.refresh();
    if (ok && then) then();
  }, [link]);

  const value = useMemo<PhoneSessionValue>(() => ({
    door,
    link: view,
    venue: asVenue(status?.venue),
    armed: status ? status.armed : null,
    unlocked,
    expiresAt: unlocked ? status?.expires_at ?? null : null,
    pinSet: status ? status.pin_set : null,
    banner,
    dismissBanner: () => show(null),
    setArmed,
    lockPhone,
    askPin,
    send,
  }), [askPin, banner, door, lockPhone, send, setArmed, show, status, unlocked, view]);

  return (
    <Ctx.Provider value={value}>
      {children}
      {pinOpen ? <PhonePinSheet door={door} pinSet={status ? status.pin_set : null} onClose={closePin} /> : null}
    </Ctx.Provider>
  );
}

export function usePhoneSession(): PhoneSessionValue {
  const value = useContext(Ctx);
  if (!value) throw new Error('usePhoneSession needs PhoneSessionProvider above it');
  return value;
}
