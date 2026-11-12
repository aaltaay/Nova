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
import { useIbkrAccountContext } from '../ibkr/IbkrAccountContext';
import { refreshIbkrStatusNow } from '../ibkr/ibkrStatusPoller';
import { setOrderDoor } from '../ibkr/orderDoor';
import { PhoneDoor, type Answer } from '../phone_link';
import { setDeskClockOffsetMs } from '../utils/deskClock';
import { createPhoneLink, type PhoneLinkView } from './phoneLink';
import { PhonePinSheet } from './PhonePinSheet';

export type BannerTone = 'sending' | 'done' | 'sent' | 'filled' | 'refused';

export interface PhoneBanner {
  tone: BannerTone;
  title: string;
  note: string;
  /** What a tap on the banner does besides closing it (a locked padlock's banner opens it). */
  onTap?: () => void;
}

/** What the desk's ticket code answers for one order or cancel. */
export interface TicketAnswer {
  ok: boolean;
  text: string;
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
  /**
   * Send one order through the desk's own ticket code (which goes out by the phone's door). The banner says
   * Sending, then Sent once the desk has answered, or NOT SENT in the desk's words, which stays. A tap while
   * one is on its way is ignored. `how: 'done'` is for a cancel: the banner then says what the desk did.
   */
  order: (label: string, run: () => Promise<TicketAnswer>, how?: 'sent' | 'done') => void;
  /** Put a banner up: a fill, a padlock that is locked. */
  notify: (banner: PhoneBanner) => void;
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
  const onItsWay = useRef(false);
  const refreshAccount = useIbkrAccountContext().refresh;

  /**
   * After a write: read the door's status now, and have the desk's own readers read too. The desk's ticket code
   * judges the padlock from the desk's status poll and sizes a sell from the account poll, so neither may wait
   * for its next turn after this phone changed one of them.
   */
  const reread = useCallback(() => {
    link.refresh();
    refreshIbkrStatusNow();
    refreshAccount();
  }, [link, refreshAccount]);

  useEffect(() => {
    link.start();
    return () => link.stop();
  }, [link]);

  // The desk's ticket code sends through this page's door, and stamps on the PC's clock.
  useEffect(() => {
    setOrderDoor({ prefix: '/api/phone', headers: () => door.sessionHeaders() });
    return () => setOrderDoor(null);
  }, [door]);
  useEffect(() => {
    setDeskClockOffsetMs(view.offsetMs);
  }, [view.offsetMs]);

  const show = useCallback((next: PhoneBanner | null) => {
    if (doneTimer.current != null) window.clearTimeout(doneTimer.current);
    doneTimer.current = null;
    setBanner(next);
    if (next && next.tone !== 'sending' && next.tone !== 'refused') {
      doneTimer.current = window.setTimeout(() => setBanner(null), DONE_MS);
    }
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
        reread();
        if (answer.ok) {
          show({ tone: 'done', title: answer.text, note: `The desk answered in ${Math.round(answer.ms)} ms` });
        } else {
          show({ tone: 'refused', title: `NOT DONE · ${label}`, note: answer.text });
        }
      });
    };
    if (door.hasSession()) run();
    else askPin(run);
  }, [askPin, door, reread, show]);

  const order = useCallback((label: string, run: () => Promise<TicketAnswer>, how: 'sent' | 'done' = 'sent') => {
    const start = (): void => {
      if (onItsWay.current) return;
      if (view.offsetMs == null) {
        show({ tone: 'refused', title: `NOT SENT · ${label}`, note: "The PC's clock is not measured yet. Wait a second and tap again." });
        return;
      }
      onItsWay.current = true;
      const tapped = performance.now();
      show({ tone: 'sending', title: `Sending · ${label}`, note: 'Waiting for the desk. A second tap is ignored.' });
      run()
        .then((answer) => {
          const ms = Math.round(performance.now() - tapped);
          if (!answer.ok) show({ tone: 'refused', title: `NOT SENT · ${label}`, note: answer.text });
          else if (how === 'done') show({ tone: 'done', title: answer.text, note: `The desk answered in ${ms} ms` });
          else show({ tone: 'sent', title: `Sent · ${label}`, note: `The desk has it · answered in ${ms} ms` });
        })
        .catch((err: unknown) => {
          console.warn('[Nova phone] an order did not get an answer', err);
          show({ tone: 'refused', title: `NOT SENT · ${label}`, note: 'Nova could not be reached. Check Orders before sending again.' });
        })
        .finally(() => {
          onItsWay.current = false;
          reread();
        });
    };
    if (door.hasSession()) start();
    else askPin(start);
  }, [askPin, door, reread, show, view.offsetMs]);

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
    order,
    notify: show,
  }), [askPin, banner, door, lockPhone, order, send, setArmed, show, status, unlocked, view]);

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
