/**
 * What every phone screen shares (ADR 070): the door to the desk (`/api/phone`), the heartbeat that
 * reads it, the banner that answers every tap, and the PIN sheets. The phone decides nothing here:
 * the venue, the padlock and every refusal are the desk's, shown as the desk words them. A venue switch
 * and a Sim step go through the desk's own handlers, so the desk and the phone move together. On Live the
 * padlock opens with the Live PIN, typed here and judged by the PC (amendment 2026-11-20).
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
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
import { PhoneDoor, type Answer, type SimClockMove } from '../phone_link';
import { simClockResource, type SimClockState } from '../sim';
import { setDeskClockOffsetMs } from '../utils/deskClock';
import { createPhoneLink, linkIsDown, type PhoneLinkView } from './phoneLink';
import { PhonePinSheet, type PinUse } from './PhonePinSheet';

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
  /** The phone may send orders on the desk's venue (every venue since 2026-11-20). Null before the first answer. */
  trades: boolean | null;
  /** Opening the padlock asks for the Live PIN: the desk is on Live. */
  armNeedsPin: boolean;
  /** This phone holds a session the backend still accepts. */
  unlocked: boolean;
  /** When that session ends, epoch seconds. */
  expiresAt: number | null;
  /** A PIN that unlocks the phone exists on the PC (the desk's own, or the phone's); null before the first answer. */
  pinSet: boolean | null;
  banner: PhoneBanner | null;
  dismissBanner: () => void;
  /**
   * Open or close the desk's padlock. Asks for the PIN first when this phone is locked; on Live, opening it asks
   * for the Live PIN, which goes to the PC with the request (the PC's own rule judges it).
   */
  setArmed: (armed: boolean) => void;
  /** End this phone's session. */
  lockPhone: () => void;
  /** Move the desk's venue (the desk's own switch). Asks for the PIN first when this phone is locked. */
  moveVenue: (next: Venue) => void;
  /** Move the Sim's playhead (the desk's own clock). The shared Sim clock takes the desk's answer at once. */
  moveSim: (label: string, move: SimClockMove) => void;
  /** Ask for the PIN; `then` runs once the phone is unlocked. */
  askPin: (then?: () => void) => void;
  /** Send one write through the door, with a banner from tap to answer. Asks for the PIN first when locked. */
  send: (label: string, write: (door: PhoneDoor) => Promise<Answer>) => void;
  /**
   * Send one order through the desk's own ticket code (which goes out by the phone's door). The banner says
   * Sending, then Sent once the desk has answered, or NOT SENT in the desk's words, which stays. A tap while
   * one is on its way is ignored. `how: 'done'` is for a cancel: the banner then says what the desk did.
   *
   * On a locked phone the tap asks for the PIN and the order is NOT sent when it opens: the bid, the ask and
   * the position moved while the PIN was typed, and a one-tap order sends what its button says at the tap.
   * The banner says to tap again.
   */
  order: (label: string, run: () => Promise<TicketAnswer>, how?: 'sent' | 'done') => void;
  /** Put a banner up: a fill, a padlock that is locked. */
  notify: (banner: PhoneBanner) => void;
  /** The No link sheet is up: reads have failed for 5 s and it was not closed, or the red pill was tapped. */
  noLinkOpen: boolean;
  closeNoLink: () => void;
  /** Open the sheet now, before the 5 s too: a tap on the red pill. */
  openNoLink: () => void;
  /** Read the door now: the sheet's Try again. */
  retryLink: () => void;
}

const Ctx = createContext<PhoneSessionValue | null>(null);

/** How long a banner that says "done" stays. A refusal stays until it is tapped. */
const DONE_MS = 4_000;

const VENUE_LABEL: Record<Venue, string> = { live: 'Live', paper: 'Paper', sim: 'Sim' };

function asVenue(value: unknown): Venue | null {
  return value === 'live' || value === 'paper' || value === 'sim' ? value : null;
}

export function PhoneSessionProvider({ children }: { children: ReactNode }) {
  const door = useMemo(() => new PhoneDoor(API_BASE_URL), []);
  const link = useMemo(() => createPhoneLink(door), [door]);
  const view = useSyncExternalStore(link.subscribe, link.get);
  const [banner, setBanner] = useState<PhoneBanner | null>(null);
  /** Which PIN sheet is up: the phone's own unlock, or the Live padlock's. */
  const [pinFor, setPinFor] = useState<PinUse | null>(null);
  const afterPin = useRef<(() => void) | null>(null);
  const doneTimer = useRef<number | null>(null);
  const onItsWay = useRef(false);
  // The No link sheet: up by itself once reads have failed long enough, closed by its X, opened by the pill.
  const [noLink, setNoLink] = useState<'auto' | 'closed' | 'open'>('auto');
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

  // A link that came back forgets the X: the next drop says so again.
  useEffect(() => {
    if (view.reachable !== false) setNoLink('auto');
  }, [view.reachable]);
  const noLinkOpen = view.reachable === false && (noLink === 'open' || (noLink === 'auto' && linkIsDown(view)));
  const closeNoLink = useCallback(() => setNoLink('closed'), []);
  const openNoLink = useCallback(() => setNoLink('open'), []);
  const retryLink = useCallback(() => link.refresh(), [link]);

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
  // Every write says the venue the screen shows (review of PR #1346), set before it is painted.
  const shownVenue = asVenue(status?.venue);
  useLayoutEffect(() => {
    door.showing(shownVenue);
  }, [door, shownVenue]);

  const askPin = useCallback((then?: () => void) => {
    afterPin.current = then ?? null;
    setPinFor('unlock');
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
    else {
      askPin(() => show({
        tone: 'done',
        title: 'Unlocked · tap again to send',
        note: `${label} was not sent: prices move while a PIN is typed.`,
      }));
    }
  }, [askPin, door, reread, show, view.offsetMs]);

  const armNeedsPin = status?.arm_requires_pin === true;
  const setArmed = useCallback((armed: boolean) => {
    // On Live the padlock opens only with the Live PIN: its own sheet sends it with the request. A locked phone
    // is unlocked first, with its own PIN, as for every other write.
    if (armed && armNeedsPin) {
      const askLive = (): void => setPinFor('live');
      if (door.hasSession()) askLive();
      else askPin(askLive);
      return;
    }
    send(armed ? 'Open the padlock' : 'Lock the padlock', (d) => d.arm(armed));
  }, [armNeedsPin, askPin, door, send]);

  const moveVenue = useCallback((next: Venue) => {
    send(`Switch to ${VENUE_LABEL[next]}`, (d) => d.moveVenue(next));
  }, [send]);

  const moveSim = useCallback((label: string, move: SimClockMove) => {
    send(label, async (d) => {
      const answer = await d.simClock(move, label);
      if (answer.ok && answer.clock) simClockResource.setData(answer.clock as SimClockState);
      return answer;
    });
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
    setPinFor(null);
    const then = afterPin.current;
    afterPin.current = null;
    link.refresh();
    if (ok && then) then();
  }, [link]);

  /**
   * The Live PIN sheet closed: the desk opened its padlock (`done`), or the operator cancelled. The banner names the
   * venue the desk answered from, so a desk that left Live while the PIN was typed is not said to be open on Live.
   */
  const closeLivePin = useCallback((done: boolean, answered?: { venue: string }) => {
    setPinFor(null);
    reread();
    if (!done) return;
    const where = asVenue(answered?.venue);
    show(where === 'live' || where == null
      ? { tone: 'done', title: 'Padlock open · LIVE', note: 'Real money: orders go to IBKR. Lock it when you put the phone down.' }
      : { tone: 'done', title: `Padlock open · ${VENUE_LABEL[where]}`, note: `The desk is on ${VENUE_LABEL[where]} now.` });
  }, [reread, show]);

  const value = useMemo<PhoneSessionValue>(() => ({
    door,
    link: view,
    venue: shownVenue,
    armed: status ? status.armed : null,
    // An older backend says `paper` only: it traded Paper alone.
    trades: status ? status.trades ?? status.paper : null,
    armNeedsPin,
    unlocked,
    expiresAt: unlocked ? status?.expires_at ?? null : null,
    pinSet: status ? status.pin_set : null,
    banner,
    dismissBanner: () => show(null),
    setArmed,
    lockPhone,
    moveVenue,
    moveSim,
    askPin,
    send,
    order,
    notify: show,
    noLinkOpen,
    closeNoLink,
    openNoLink,
    retryLink,
  }), [armNeedsPin, askPin, banner, closeNoLink, door, lockPhone, moveSim, moveVenue, noLinkOpen, openNoLink, order, retryLink, send, setArmed, show, shownVenue, status, unlocked, view]);

  return (
    <Ctx.Provider value={value}>
      {children}
      {pinFor ? (
        <PhonePinSheet
          key={pinFor}
          door={door}
          use={pinFor}
          pinSet={status ? status.pin_set : null}
          onClose={pinFor === 'live' ? closeLivePin : closePin}
        />
      ) : null}
    </Ctx.Provider>
  );
}

export function usePhoneSession(): PhoneSessionValue {
  const value = useContext(Ctx);
  if (!value) throw new Error('usePhoneSession needs PhoneSessionProvider above it');
  return value;
}
