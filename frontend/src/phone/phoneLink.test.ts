import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { PhoneStatus } from '../phone_link';
import { BEAT_EVERY_MS, BEAT_MISS_MS, WAITING, createPhoneLink, linkText, linkTone, type BeatSource } from './phoneLink';

const STATUS: PhoneStatus = { pin_set: true, unlocked: false, expires_at: null, venue: 'paper', paper: true, armed: false };

/** A page that can be hidden and shown. */
function fakeDoc(): Document & { setHidden(hidden: boolean): void } {
  const target = new EventTarget();
  let hidden = false;
  Object.defineProperty(target, 'hidden', { get: () => hidden });
  return Object.assign(target, {
    setHidden(next: boolean) {
      hidden = next;
      target.dispatchEvent(new Event('visibilitychange'));
    },
  }) as unknown as Document & { setHidden(hidden: boolean): void };
}

/** A door whose next answers are scripted: a status, or null for "the PC did not answer". */
function door(answers: Array<{ status: PhoneStatus | null; ms: number }>): BeatSource & { asked: number } {
  const self = {
    asked: 0,
    beat: () => {
      self.asked += 1;
      const next = answers.shift() ?? { status: STATUS, ms: 40 };
      return Promise.resolve({ ...next, asked: Date.now() });
    },
  };
  return self;
}

describe("the phone's heartbeat", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-11-11T14:31:00Z'));
  });
  afterEach(() => vi.useRealTimers());

  it("keeps the desk's venue and padlock, and the round trip of the last 30 seconds", async () => {
    const d = door([{ status: { ...STATUS, armed: true }, ms: 41 }, { status: STATUS, ms: 77 }]);
    const link = createPhoneLink(d, fakeDoc());
    expect(link.get()).toBe(WAITING);
    link.start();
    await vi.advanceTimersByTimeAsync(0);
    expect(link.get()).toMatchObject({ reachable: true, status: { venue: 'paper', armed: true }, drops: 0 });
    expect(linkText(link.get())).toBe('41 ms');
    await vi.advanceTimersByTimeAsync(BEAT_EVERY_MS);
    expect(link.get().status?.armed).toBe(false);
    expect(link.get().roundTrip).toMatchObject({ n: 2, max: 77 });
    expect(linkTone(link.get())).toBe('good');
    link.stop();
  });

  it("measures the PC's clock against the phone's from the answer's own time", async () => {
    // The PC answers that it is 2 s later than the phone thinks, on a 100 ms round trip.
    const pcNow = Date.now() / 1000 + 2;
    const link = createPhoneLink(door([{ status: { ...STATUS, now: pcNow }, ms: 100 }]), fakeDoc());
    link.start();
    await vi.advanceTimersByTimeAsync(0);
    // The answer left the PC mid round trip: 2000 ms minus half of 100.
    expect(link.get().offsetMs).toBeCloseTo(1950, 0);
    link.stop();
  });

  it('says No link when the PC stops answering, keeps what it last knew, and counts the drop once', async () => {
    const d = door([{ status: { ...STATUS, armed: true }, ms: 40 }, { status: null, ms: 8000 }, { status: null, ms: 8000 }, { status: STATUS, ms: 40 }]);
    const link = createPhoneLink(d, fakeDoc());
    link.start();
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(BEAT_EVERY_MS);
    expect(link.get()).toMatchObject({ reachable: false, drops: 1, status: { armed: true } });
    expect(linkTone(link.get())).toBe('down');
    expect(linkText(link.get())).toBe('No link');
    await vi.advanceTimersByTimeAsync(BEAT_EVERY_MS);
    expect(link.get().drops).toBe(1);
    await vi.advanceTimersByTimeAsync(BEAT_EVERY_MS);
    expect(link.get()).toMatchObject({ reachable: true, drops: 1 });
    link.stop();
  });

  it('counts an answer slower than the miss limit as no answer', async () => {
    const link = createPhoneLink(door([{ status: STATUS, ms: BEAT_MISS_MS + 1 }]), fakeDoc());
    link.start();
    await vi.advanceTimersByTimeAsync(0);
    expect(link.get()).toMatchObject({ reachable: false, drops: 1 });
    link.stop();
  });

  it('turns amber when 95 in 100 round trips are over the order limit', async () => {
    const link = createPhoneLink(door([{ status: STATUS, ms: 900 }]), fakeDoc());
    link.start();
    await vi.advanceTimersByTimeAsync(0);
    expect(linkTone(link.get())).toBe('slow');
    link.stop();
  });

  it('reads nothing while the page is hidden, and reads at once when it shows again', async () => {
    const doc = fakeDoc();
    const d = door([]);
    const link = createPhoneLink(d, doc);
    link.start();
    await vi.advanceTimersByTimeAsync(0);
    expect(d.asked).toBe(1);
    doc.setHidden(true);
    await vi.advanceTimersByTimeAsync(5 * BEAT_EVERY_MS);
    expect(d.asked).toBe(1);
    doc.setHidden(false);
    await vi.advanceTimersByTimeAsync(0);
    expect(d.asked).toBe(2);
    expect(link.get().drops).toBe(0);
    link.stop();
  });

  it('tells its listeners, and stops when stopped', async () => {
    const d = door([]);
    const link = createPhoneLink(d, fakeDoc());
    const heard = vi.fn();
    const off = link.subscribe(heard);
    link.start();
    await vi.advanceTimersByTimeAsync(0);
    expect(heard).toHaveBeenCalledTimes(1);
    off();
    link.stop();
    await vi.advanceTimersByTimeAsync(3 * BEAT_EVERY_MS);
    expect(d.asked).toBe(1);
    expect(heard).toHaveBeenCalledTimes(1);
  });
});
