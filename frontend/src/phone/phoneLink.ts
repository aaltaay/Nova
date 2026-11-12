/**
 * The phone's heartbeat (ADR 070): once a second it reads the door's status, and from that one read
 * keeps what every screen's header shows -- the desk's venue, the padlock, whether this phone is
 * unlocked -- and how good the link is: the round trip over the last 30 seconds, the phone's clock
 * against the PC's, and how many times the PC stopped answering. No React here; `PhoneSession.tsx`
 * hands it to the screens.
 *
 * A hidden page measures nothing: the browser freezes it, so no read is sent, a read in flight
 * across a hide is thrown away, and a drop does not grow over the time the screen was off.
 */
import {
  CLOCK_SAMPLES_KEEP,
  LINK_LIMIT_MS,
  Outages,
  Rolling,
  bestClock,
  clockSample,
  type ClockSample,
  type PhoneStatus,
  type Spread,
} from '../phone_link';

export const BEAT_EVERY_MS = 1_000;
/** A read that takes longer than this is a miss: the next one is already due. */
export const BEAT_MISS_MS = 3_000;

export type LinkTone = 'good' | 'slow' | 'down' | 'waiting';

export interface PhoneLinkView {
  /** The door's last answer. Kept while the PC is not answering, so the screen says what it last knew. */
  status: PhoneStatus | null;
  /** Null before the first answer; false while reads fail. */
  reachable: boolean | null;
  /** The last 30 seconds of round trips, ms. */
  roundTrip: Spread | null;
  /** The PC's clock minus this device's, ms; null before the first answer that carried the PC's clock. */
  offsetMs: number | null;
  /** Times the PC stopped answering since this page opened. */
  drops: number;
}

export const WAITING: PhoneLinkView = { status: null, reachable: null, roundTrip: null, offsetMs: null, drops: 0 };

/** Green under the order door's limit, amber over it, red when the PC does not answer. */
export function linkTone(view: PhoneLinkView): LinkTone {
  if (view.reachable === false) return 'down';
  if (view.reachable == null || !view.roundTrip) return 'waiting';
  return view.roundTrip.p95 <= LINK_LIMIT_MS ? 'good' : 'slow';
}

/** The pill's number: the middle round trip of the last 30 seconds. */
export function linkText(view: PhoneLinkView): string {
  if (view.reachable === false) return 'No link';
  if (!view.roundTrip) return '…';
  return `${Math.round(view.roundTrip.p50)} ms`;
}

export interface BeatSource {
  beat(): Promise<{ status: PhoneStatus | null; ms: number; asked: number }>;
}

export interface PhoneLink {
  start(): void;
  stop(): void;
  /** Read the status now: after an unlock, a lock or a padlock tap, so the header does not wait a second. */
  refresh(): void;
  get(): PhoneLinkView;
  subscribe(listener: () => void): () => void;
}

export function createPhoneLink(door: BeatSource, doc: Document = document): PhoneLink {
  let view = WAITING;
  const listeners = new Set<() => void>();
  const roundTrips = new Rolling();
  const outages = new Outages();
  let clock: ClockSample[] = [];
  let timer: number | null = null;
  let hiddenAt: number | null = null;
  /** Counts every hide and show: a read in flight across one measured the browser, not the link. */
  let span = 0;
  let inFlight = false;

  const publish = (next: PhoneLinkView): void => {
    view = next;
    listeners.forEach((fn) => fn());
  };

  const beat = async (): Promise<void> => {
    if (hiddenAt != null || inFlight) return;
    inFlight = true;
    const asked = span;
    const answer = await door.beat();
    inFlight = false;
    if (timer == null || asked !== span) return;
    const now = Date.now();
    const ok = answer.status != null && answer.ms <= BEAT_MISS_MS;
    if (ok) {
      outages.up(now);
      roundTrips.add(now, answer.ms);
      const pcNow = answer.status?.now;
      if (typeof pcNow === 'number') {
        clock = [...clock, clockSample(answer.asked, answer.asked + answer.ms, pcNow)].slice(-CLOCK_SAMPLES_KEEP);
      }
    } else {
      outages.down(now);
    }
    publish({
      status: answer.status ?? view.status,
      reachable: ok,
      roundTrip: roundTrips.spread(now),
      offsetMs: bestClock(clock)?.offsetMs ?? null,
      drops: outages.count,
    });
  };

  const onVisibility = (): void => {
    const now = Date.now();
    span += 1;
    if (doc.hidden) {
      if (hiddenAt == null) hiddenAt = now;
      return;
    }
    if (hiddenAt != null) outages.skip(hiddenAt, now);
    hiddenAt = null;
    void beat();
  };

  return {
    start() {
      if (timer != null) return;
      hiddenAt = doc.hidden ? Date.now() : null;
      doc.addEventListener('visibilitychange', onVisibility);
      timer = window.setInterval(() => void beat(), BEAT_EVERY_MS);
      void beat();
    },
    stop() {
      if (timer == null) return;
      window.clearInterval(timer);
      timer = null;
      doc.removeEventListener('visibilitychange', onVisibility);
    },
    refresh() {
      void beat();
    },
    get: () => view,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}
