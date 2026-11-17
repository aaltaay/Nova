import { describe, expect, it } from 'vitest';
import { WAITING, type PhoneLinkView } from './phoneLink';
import { agoWords, clockWords, lastAnswerWords, noLinkWords, oldDataWords } from './noLinkWords';

/** 09:00 on this machine's clock, and a view made 8 h 43 min after its last answer. */
const LAST = new Date(2026, 10, 17, 5, 14, 0).getTime();
const NOW = LAST + (8 * 60 + 43) * 60_000;
const down = (over: Partial<PhoneLinkView>): PhoneLinkView => ({
  ...WAITING, reachable: false, why: 'pc', lastAnswerAt: LAST, downSince: NOW - 6_000, at: NOW, ...over,
});

describe('the No link sheet words', () => {
  it('says how long ago in the units a glance needs', () => {
    expect(agoWords(40_000)).toBe('40 s ago');
    expect(agoWords(3 * 60_000 + 10_000)).toBe('3 min ago');
    expect(agoWords((8 * 60 + 43) * 60_000)).toBe('8 h 43 min ago');
    expect(agoWords(50 * 3_600_000)).toBe('2 d ago');
    expect(agoWords(-5)).toBe('0 s ago');
  });

  it("writes a time on the phone's clock, with the day when it is not today", () => {
    expect(clockWords(LAST, NOW)).toBe('5:14 AM');
    expect(clockWords(LAST, NOW + 24 * 3_600_000)).toBe('Nov 17, 5:14 AM');
  });

  it('says when the PC last answered, and how old the screen is', () => {
    expect(lastAnswerWords(down({}))).toBe('Last answer 5:14 AM, 8 h 43 min ago');
    expect(oldDataWords(down({}))).toBe('Showing 5:14 AM. Not live.');
  });

  it('claims no time when the PC has not answered since the page opened', () => {
    expect(lastAnswerWords(down({ lastAnswerAt: null }))).toBe('No answer since this page opened');
    expect(oldDataWords(down({ lastAnswerAt: null }))).toBe('Not live.');
  });

  it('no answer at all: Tailscale first, then the PC, and offers to open Tailscale', () => {
    const words = noLinkWords(down({ why: 'pc' }));
    expect(words).toMatchObject({ kind: 'pc', title: "Can't reach your PC", tailscale: true });
    expect(words.steps).toEqual(['Turn Tailscale on, on this phone.', 'Still nothing? The PC is off or asleep.']);
  });

  it("the tunnel's own answer: Nova is not running, and Tailscale is not the fix", () => {
    for (const http of [502, 503, 504]) {
      const words = noLinkWords(down({ why: 'nova', http }));
      expect(words).toMatchObject({ kind: 'nova-down', title: "Nova isn't running on the PC", tailscale: false });
      expect(words.sub).toBe("The PC answers, Nova doesn't. Last answer 5:14 AM, 8 h 43 min ago");
      expect(words.steps[0]).toBe('Start Nova on the PC.');
    }
  });

  it('any other answer that is not Nova at work: says the code, never that Nova is off', () => {
    const words = noLinkWords(down({ why: 'nova', http: 400 }));
    expect(words).toMatchObject({ kind: 'nova-error', title: 'Nova answered with an error', tailscale: false });
    expect(words.sub).toContain("The PC's answer was 400.");
  });

  it('a phone with no network says so, whatever else is true', () => {
    const words = noLinkWords(down({ why: 'offline' }));
    expect(words).toMatchObject({ kind: 'offline', title: 'This phone is offline', sub: 'No Wi-Fi or mobile data', tailscale: false });
  });
});
