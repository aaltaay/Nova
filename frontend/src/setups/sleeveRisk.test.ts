/**
 * @vitest-environment jsdom
 *
 * The venue sleeve's risk per trade (ADR 042 draft): the session read, the venue's own sleeve, what a reader
 * shows when it is not the sleeve's (and why), and a read that answers from before a save never undoes it.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NOVA_API_KEY_STORAGE } from '../constantGroups/api_auth';
import {
  _resetSleeveForTests,
  capsFor,
  getSleeveSnap,
  parseSleeve,
  readSleeveNow,
  saveSleeveRisk,
  sleeveRiskOf,
  type SleeveSnap,
} from './sleeveRisk';

const session = (risk: number | null, venue = 'paper', byVenue: Record<string, unknown> = {}) => ({
  caps: { venue, ...(risk === null ? {} : { risk_usd: risk }), working_ttl_sec: 4 },
  caps_bounds: { risk_usd: [1, 5000] },
  caps_by_venue: byVenue,
});

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem(NOVA_API_KEY_STORAGE, 'desk-key');
  _resetSleeveForTests();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the sleeve on the wire', () => {
  it("reads the desk venue's risk, every venue's, the time limit and the bounds", () => {
    const s = parseSleeve(session(25, 'paper', { live: { risk_usd: 10 }, sim: { venue: 'sim', risk_usd: 15 } }));
    expect(s?.state).toBe('ok');
    expect(s?.caps).toEqual({ venue: 'paper', riskUsd: 25, ttlSec: 4 });
    expect(s?.byVenue.live).toEqual({ venue: 'live', riskUsd: 10, ttlSec: null });
    expect(s?.bounds).toEqual([1, 5000]);
    // A session without a risk per trade is a backend before ADR 042; anything else is not a session.
    expect(parseSleeve(session(null))?.state).toBe('older');
    expect(parseSleeve({ level: 2 })).toBeNull();
    expect(parseSleeve(null)).toBeNull();
  });

  it("picks the venue's own sleeve, else the desk venue's only when it is that venue", () => {
    const snap = { ...getSleeveSnap(), ...parseSleeve(session(25, 'paper', { sim: { risk_usd: 15 } }))! } as SleeveSnap;
    expect(capsFor(snap, 'sim')?.riskUsd).toBe(15);
    expect(capsFor(snap, 'paper')?.riskUsd).toBe(25);
    expect(capsFor(snap, null)?.riskUsd).toBe(25);
    expect(capsFor(snap, 'live')).toBeNull();          // never another venue's number
  });
});

describe('what a reader shows', () => {
  it("is the sleeve's when it has one, and otherwise says whose number sizes and why", () => {
    const ok = { ...getSleeveSnap(), ...parseSleeve(session(25))! } as SleeveSnap;
    expect(sleeveRiskOf(ok, 'paper', 40)).toMatchObject({ riskUsd: 25, source: 'sleeve', venue: 'paper', why: null, ttlSec: 4 });
    const older = { ...getSleeveSnap(), ...parseSleeve(session(null))! } as SleeveSnap;
    expect(sleeveRiskOf(older, 'paper', 40)).toMatchObject({ riskUsd: 40, source: 'local' });
    expect(sleeveRiskOf(older, 'paper', 40).why).toMatch(/keeps no risk per trade .* your \$40 saved on this desk/);
    const failed: SleeveSnap = { ...getSleeveSnap(), state: 'error', error: "The bot's sleeve could not be read: HTTP 500." };
    expect(sleeveRiskOf(failed, null, null)).toMatchObject({ riskUsd: 20, source: 'default' });
    expect(sleeveRiskOf(failed, null, null).why).toBe("The bot's sleeve could not be read: HTTP 500. Sizing at the $20 default.");
    expect(sleeveRiskOf(getSleeveSnap(), 'sim', null).why).toMatch(/^Reading the risk per trade from the Sim sleeve/);
  });
});

describe('reading and saving', () => {
  it('a read that answers from before a save is dropped: the save is newer', async () => {
    let answerRead: (r: Response) => void = () => undefined;
    vi.stubGlobal('fetch', vi.fn((input: unknown, init?: RequestInit) => {
      if (init?.method === 'PATCH') {
        return Promise.resolve(new Response(JSON.stringify(session(40)), { status: 200 }));
      }
      expect(String(input)).toMatch(/\/api\/bot\/session$/);
      return new Promise<Response>(resolve => { answerRead = resolve; });
    }));
    const read = readSleeveNow();                         // in flight: answers later with the old $20
    expect(await saveSleeveRisk(40, 'paper')).toBeNull();
    expect(capsFor(getSleeveSnap(), 'paper')?.riskUsd).toBe(40);
    answerRead(new Response(JSON.stringify(session(20)), { status: 200 }));
    await read;
    expect(capsFor(getSleeveSnap(), 'paper')?.riskUsd).toBe(40);
  });

  it('says when the sleeve kept another number than the one asked', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(session(5000)), { status: 200 })));
    await readSleeveNow();
    expect(await saveSleeveRisk(9000, 'paper')).toBe('The Paper sleeve kept $5,000, not $9,000.');
    expect(getSleeveSnap().saveError).toBe('The Paper sleeve kept $5,000, not $9,000.');
  });

  it('a refusal is said in the backend\'s own words, never as saved', async () => {
    vi.stubGlobal('fetch', vi.fn(async (_input: unknown, init?: RequestInit) => (init?.method === 'PATCH'
      ? new Response(JSON.stringify({ detail: { reason: 'BOT_CAPS_INVALID', error: 'risk_usd is 1 to 10000' } }), { status: 400 })
      : new Response(JSON.stringify(session(20)), { status: 200 }))));
    await readSleeveNow();
    expect(await saveSleeveRisk(40, 'paper')).toBe('The risk per trade was not saved: risk_usd is 1 to 10000');
    expect(capsFor(getSleeveSnap(), 'paper')?.riskUsd).toBe(20);
  });
});
