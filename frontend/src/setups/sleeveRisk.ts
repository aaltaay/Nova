/**
 * Risk per trade lives in the bot's sleeve (ADR 042 draft, spec E): each venue keeps its own `caps.risk_usd`,
 * read from `GET /api/bot/session` and changed with `PATCH /api/bot/session {caps: {venue, risk_usd}}`. Nova's
 * automatic buys (the bot, Auto-entry) size by it, and so do the Trader plan's Stage and Approve and every
 * proposal's Stage, so one number sizes every buy on the venue. One store per window, read while a live
 * Trader tab or the setup alert card shows it. The desk's old local value (`nova.stockRead.riskUsd`) moves
 * into the desk venue's sleeve once and is then deleted; a backend that refuses it keeps the key, and every
 * reader says so.
 *
 * When the sleeve cannot be read the operator's own ticket is still sized, from the old local value or the
 * default, and every reader says which and why: never a number passed off as the sleeve's.
 */
import { useEffect, useMemo, useSyncExternalStore } from 'react';
import { novaFetch } from '../api/novaFetch';
import {
  API_BASE_URL,
  SLEEVE_POLL_MS,
  SLEEVE_RISK_DEFAULT_USD,
  SLEEVE_RISK_LEGACY_KEY,
  SLEEVE_RISK_MAX_USD,
  SLEEVE_SESSION_PATH,
} from '../constants';
import { SAMPLE_WRITE_REFUSAL } from '../sample_data/sampleCopy';
import { onSampleDesk } from '../sample_data/sampleOrderGuard';
import { readPref, writePref } from '../utils/prefStore';

export type SleeveVenue = 'live' | 'paper' | 'sim';

export const VENUE_NAMES: Record<SleeveVenue, string> = { live: 'Live', paper: 'Paper', sim: 'Sim' };

/** One venue's sleeve as far as sizing reads it. */
export interface SleeveCaps {
  venue: SleeveVenue | null;
  riskUsd: number | null;
  /** Every Nova entry is cancelled unfilled after this many seconds (one TTL, spec E). */
  ttlSec: number | null;
}

export interface SleeveSnap {
  /** `ok`: read with a risk per trade; `older`: the session carries none (a backend before ADR 042);
   * `error`: the read failed; `idle`: not read yet. */
  state: 'idle' | 'ok' | 'older' | 'error';
  /** The desk venue's sleeve, as the last read answered. */
  caps: SleeveCaps | null;
  byVenue: Partial<Record<SleeveVenue, SleeveCaps>>;
  bounds: readonly [number, number];
  error: string | null;
  saving: boolean;
  saveError: string | null;
  /** The old local value could not move into the sleeve: why, in words. */
  moveError: string | null;
}

type Obj = Record<string, unknown>;

const DEFAULT_BOUNDS: readonly [number, number] = [1, SLEEVE_RISK_MAX_USD];

const INITIAL: SleeveSnap = {
  state: 'idle', caps: null, byVenue: {}, bounds: DEFAULT_BOUNDS, error: null, saving: false, saveError: null,
  moveError: null,
};

function obj(v: unknown): Obj | null {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Obj) : null;
}

function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

/** The dollars of risk the desk accepts: positive, at most the sleeve's own ceiling, to the cent. */
export function parseRiskUsd(raw: unknown): number | null {
  const n = typeof raw === 'number' ? raw : typeof raw === 'string' ? Number(raw.replace(/[$,\s]/g, '')) : NaN;
  return Number.isFinite(n) && n > 0 && n <= SLEEVE_RISK_MAX_USD ? Math.round(n * 100) / 100 : null;
}

function venueOf(v: unknown): SleeveVenue | null {
  return v === 'live' || v === 'paper' || v === 'sim' ? v : null;
}

export function venueOrNull(v: string | null | undefined): SleeveVenue | null {
  return venueOf(v);
}

function capsOf(raw: unknown, venue: SleeveVenue | null): SleeveCaps | null {
  const c = obj(raw);
  if (!c) return null;
  const risk = num(c.risk_usd);
  return {
    venue: venueOf(c.venue) ?? venue,
    riskUsd: risk !== null && risk > 0 ? risk : null,
    ttlSec: num(c.working_ttl_sec),
  };
}

type SleeveRead = Pick<SleeveSnap, 'caps' | 'byVenue' | 'bounds' | 'state'>;

/** The sleeve part of a bot session; null when the answer is not a session. */
export function parseSleeve(raw: unknown): SleeveRead | null {
  const s = obj(raw);
  if (!s || !obj(s.caps)) return null;
  const caps = capsOf(s.caps, null);
  const byVenue: Partial<Record<SleeveVenue, SleeveCaps>> = {};
  const all = obj(s.caps_by_venue);
  for (const v of ['live', 'paper', 'sim'] as const) {
    const c = capsOf(all?.[v], v);
    if (c) byVenue[v] = c;
  }
  const b = obj(s.caps_bounds)?.risk_usd;
  const lo = Array.isArray(b) ? num(b[0]) : null;
  const hi = Array.isArray(b) ? num(b[1]) : null;
  const bounds: readonly [number, number] = lo !== null && hi !== null && lo > 0 && hi >= lo ? [lo, hi] : DEFAULT_BOUNDS;
  return { caps, byVenue, bounds, state: caps?.riskUsd != null ? 'ok' : 'older' };
}

/** The venue's sleeve: its own entry, else the desk venue's when it is that venue (or none is named). */
export function capsFor(s: SleeveSnap, venue: SleeveVenue | null): SleeveCaps | null {
  if (venue && s.byVenue[venue]) return s.byVenue[venue] ?? null;
  if (!venue || !s.caps?.venue || s.caps.venue === venue) return s.caps;
  return null;
}

/** The backend's refusal in its own words (`{detail: {reason, error}}` or a plain detail). */
function refusal(status: number, body: unknown): string {
  if (status === 401 || status === 503) {
    return 'The desk has no API key for this: Nova needs NOVA_API_KEY to save the risk per trade.';
  }
  const detail = obj(body)?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail.trim();
  const d = obj(detail);
  for (const k of ['error', 'detail', 'reason']) {
    const v = d?.[k];
    if (typeof v === 'string' && v.trim()) return v.trim();
  }
  return `The desk answered ${status}.`;
}

// -- the store --------------------------------------------------------------------------------
let snap: SleeveSnap = INITIAL;
const listeners = new Set<() => void>();
let readers = 0;
let timer: number | null = null;
let inFlight: Promise<void> | null = null;
let moveTried = false;
/** Bumped by every save: a read that started before it answers from before it, and is dropped. */
let writeEpoch = 0;
/** The desk's own (old) risk per trade, read once per window: undefined until read. */
let localRisk: number | null | undefined;

function publish(next: SleeveSnap): void {
  snap = next;
  for (const fn of [...listeners]) fn();
}

export function getSleeveSnap(): SleeveSnap {
  return snap;
}

export function subscribeSleeve(fn: () => void): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

function legacyRisk(): number | null {
  if (localRisk === undefined) localRisk = readPref<number | null>(SLEEVE_RISK_LEGACY_KEY, null, parseRiskUsd);
  return localRisk;
}

function writeLegacy(value: number): void {
  writePref(SLEEVE_RISK_LEGACY_KEY, value);
  localRisk = value;
}

function dropLegacy(): void {
  localRisk = null;
  try {
    localStorage.removeItem(SLEEVE_RISK_LEGACY_KEY);
  } catch (e) {
    console.warn('[Nova] the old risk per trade could not be removed from this desk', e);
  }
}

/** Read the session once (a read in flight is shared). */
export function readSleeveNow(): Promise<void> {
  if (onSampleDesk()) return Promise.resolve();
  if (inFlight) return inFlight;
  const epoch = writeEpoch;
  inFlight = (async () => {
    try {
      const res = await fetch(`${API_BASE_URL}${SLEEVE_SESSION_PATH}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const parsed = parseSleeve(await res.json());
      if (!parsed) throw new Error('the answer is not a bot session');
      if (epoch !== writeEpoch) return;              // a save answered since: its sleeve is newer
      publish({ ...snap, ...parsed, error: null });
      if (parsed.state === 'ok') void moveLegacy();
    } catch (e) {
      // A failed read keeps the last good sleeve on screen and says so.
      publish({ ...snap, state: snap.state === 'ok' ? 'ok' : 'error',
        error: `The bot's sleeve could not be read: ${e instanceof Error ? e.message : String(e)}.` });
    } finally {
      inFlight = null;
    }
  })();
  return inFlight;
}

/** Keep reading while something on screen shows the risk; the returned function stops this reader. */
export function readSleeveWhileShown(): () => void {
  readers += 1;
  if (readers === 1) {
    void readSleeveNow();
    timer = window.setInterval(() => void readSleeveNow(), SLEEVE_POLL_MS);
  }
  return () => {
    readers = Math.max(0, readers - 1);
    if (readers === 0 && timer !== null) {
      window.clearInterval(timer);
      timer = null;
    }
  };
}

async function patchRisk(value: number, venue: SleeveVenue | null): Promise<SleeveRead> {
  if (onSampleDesk()) throw new Error(SAMPLE_WRITE_REFUSAL);
  writeEpoch += 1;
  const res = await novaFetch(`${API_BASE_URL}${SLEEVE_SESSION_PATH}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ caps: venue ? { venue, risk_usd: value } : { risk_usd: value } }),
  });
  const json: unknown = await res.json().catch(() => null);
  if (!res.ok) throw new Error(refusal(res.status, json));
  const parsed = parseSleeve(json);
  if (!parsed) throw new Error("The desk's answer to the risk per trade was not a bot session.");
  return parsed;
}

const usd = (v: number) => `$${v.toLocaleString('en-US', { maximumFractionDigits: 2 })}`;

function sleeveName(venue: SleeveVenue | null): string {
  return venue ? `the ${VENUE_NAMES[venue]} sleeve` : 'the desk venue\'s sleeve';
}

/**
 * Save the venue's risk per trade. On a backend that keeps none in the sleeve it is kept on this desk, as
 * before. Resolves with the refusal in words, or null when saved as asked.
 */
export async function saveSleeveRisk(value: number, venue: SleeveVenue | null): Promise<string | null> {
  if (snap.state === 'older') {
    writeLegacy(value);
    publish({ ...snap, saveError: null });
    return null;
  }
  publish({ ...snap, saving: true, saveError: null });
  try {
    const parsed = await patchRisk(value, venue);
    if (parsed.state === 'older') {
      writeLegacy(value);
      const why = 'This backend keeps no risk per trade in the bot\'s sleeve: it is saved on this desk. Reload the backend.';
      publish({ ...snap, ...parsed, saving: false, saveError: why });
      return why;
    }
    const next = { ...snap, ...parsed, saving: false, error: null };
    const kept = capsFor(next, venue)?.riskUsd ?? null;
    const saveError = kept !== null && Math.abs(kept - value) > 0.005
      ? `${capital(sleeveName(venue))} kept ${usd(kept)}, not ${usd(value)}.`
      : null;
    publish({ ...next, saveError });
    return saveError;
  } catch (e) {
    const why = `The risk per trade was not saved: ${e instanceof Error ? e.message : String(e)}`;
    publish({ ...snap, saving: false, saveError: why });
    return why;
  }
}

function capital(s: string): string {
  return s ? `${s[0].toUpperCase()}${s.slice(1)}` : s;
}

/** The old local risk per trade moves into the desk venue's sleeve once per window, then its key goes. */
async function moveLegacy(): Promise<void> {
  if (moveTried || onSampleDesk()) return;
  moveTried = true;
  const old = legacyRisk();
  if (old === null) return;
  const venue = snap.caps?.venue ?? null;
  if (snap.caps?.riskUsd != null && Math.abs(snap.caps.riskUsd - old) <= 0.005) {
    dropLegacy();
    return;
  }
  try {
    const parsed = await patchRisk(old, venue);
    const next = { ...snap, ...parsed };
    const kept = capsFor(next, venue)?.riskUsd ?? null;
    if (kept !== null && Math.abs(kept - old) <= 0.005) {
      dropLegacy();
      publish({ ...next, moveError: null });
      return;
    }
    publish({ ...next, moveError: `Your ${usd(old)} risk per trade, saved on this desk, did not move into `
      + `${sleeveName(venue)} (it kept ${kept === null ? 'none' : usd(kept)}).` });
  } catch (e) {
    const why = e instanceof Error ? e.message : String(e);
    console.warn('[Nova] the old risk per trade could not move into the sleeve', why);
    publish({ ...snap, moveError: `Your ${usd(old)} risk per trade, saved on this desk, could not move into `
      + `${sleeveName(venue)}: ${why}` });
  }
}

// -- what a reader shows ------------------------------------------------------------------------
export interface SleeveRisk {
  /** What sizes the operator's own buys: the sleeve's, else the old local value, else the default. */
  riskUsd: number;
  source: 'sleeve' | 'local' | 'default';
  /** Whose sleeve, when it is the sleeve's. */
  venue: SleeveVenue | null;
  /** Why the number is not the sleeve's, or the sleeve's trouble: null when all is well. */
  why: string | null;
  ttlSec: number | null;
  bounds: readonly [number, number];
  saving: boolean;
  saveError: string | null;
  moveError: string | null;
}

/** Pure: the risk a reader on `venue` shows. */
export function sleeveRiskOf(s: SleeveSnap, venue: SleeveVenue | null, local: number | null): SleeveRisk {
  const caps = capsFor(s, venue);
  const base = { ttlSec: caps?.ttlSec ?? null, bounds: s.bounds, saving: s.saving, saveError: s.saveError,
    moveError: s.moveError };
  if (caps?.riskUsd != null) {
    return { ...base, riskUsd: caps.riskUsd, source: 'sleeve', venue: caps.venue ?? venue, why: s.error };
  }
  const fallback = local !== null ? `your ${usd(local)} saved on this desk` : `the ${usd(SLEEVE_RISK_DEFAULT_USD)} default`;
  const name = sleeveName(venue);
  const why = s.state === 'older'
    ? `This backend keeps no risk per trade in the bot's sleeve yet: sizing at ${fallback}. Reload the backend.`
    : s.state === 'error'
      ? `${s.error ?? 'The bot\'s sleeve could not be read.'} Sizing at ${fallback}.`
      : s.state === 'ok'
        ? `${capital(name)} gave no risk per trade: sizing at ${fallback}.`
        : `Reading the risk per trade from ${name}: sizing at ${fallback} meanwhile.`;
  return { ...base, riskUsd: local ?? SLEEVE_RISK_DEFAULT_USD, source: local !== null ? 'local' : 'default',
    venue: null, why };
}

/** Where a size's risk per trade came from, in a few words ("the Paper sleeve's"). */
export function riskSourceWords(r: SleeveRisk): string {
  if (r.source === 'sleeve') return r.venue ? `the ${VENUE_NAMES[r.venue]} sleeve's` : 'the sleeve\'s';
  return r.source === 'local' ? 'saved on this desk, not the sleeve\'s' : 'the default, not the sleeve\'s';
}

/** The risk per trade on `venue`, read while `active` (never on the sample desk). */
export function useSleeveRisk(venue: SleeveVenue | null, active: boolean): SleeveRisk {
  const s = useSyncExternalStore(subscribeSleeve, getSleeveSnap, getSleeveSnap);
  useEffect(() => {
    if (!active || onSampleDesk()) return;
    return readSleeveWhileShown();
  }, [active]);
  useEffect(() => {
    if (active && venue && !onSampleDesk()) void readSleeveNow();   // a venue change reads its sleeve now
  }, [active, venue]);
  const local = legacyRisk();
  // One object per answer: a Trader tab's ticks redraw no reader of it.
  return useMemo(() => sleeveRiskOf(s, venue, local), [s, venue, local]);
}

export function _resetSleeveForTests(): void {
  if (timer !== null) window.clearInterval(timer);
  timer = null;
  readers = 0;
  inFlight = null;
  moveTried = false;
  writeEpoch = 0;
  localRisk = undefined;
  snap = INITIAL;
}
