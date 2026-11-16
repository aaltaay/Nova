/**
 * The close-of-day reminder (operator ask, 2026-10-01): a loud card at
 * 15:50 ET for each Paper or Live position still open, escalated at 15:55, gone at 16:00, so the
 * desk is flat by the close. Once per position per day per stage: a dismissed card does not come
 * back at the same stage (the fired keys are kept for the day in localStorage), a position that
 * goes flat takes its card with it. Sim is left out -- its clock is the replay playhead. Another
 * trader's shares on Paper (Claude's, the brain's, a retired bot's) get a card of their own per trader at 15:56
 * (ADR 072), the net under never holding overnight: Nova's 15:55 sale of a trader's shares runs by then, so it
 * shows only when that sale did not finish. Shares handed to you are yours, on your card.
 * Weekends are out; there is no holiday calendar on the client, and a holiday afternoon has no
 * positions changing hands to remind about. Nothing here places, stages or cancels an order.
 */
import type { Owner } from '../constantGroups/owners';
import { readPref, writePref } from '../utils/prefStore';
import {
  CLOSE_REMIND_CLOSE_MIN_ET,
  CLOSE_REMIND_FINAL_MIN_ET,
  CLOSE_REMIND_FIRED_PREF_KEY,
  CLOSE_REMIND_FIRED_SCHEMA_VERSION,
  CLOSE_REMIND_OTHERS_MIN_ET,
  CLOSE_REMIND_WARN_MIN_ET,
} from './closeReminderConstants';

export type CloseReminderStage = 'warn' | 'final' | 'others';
export type CloseReminderVenue = 'live' | 'paper';

/** What the cards need of a position row (IbkrPosition is structurally one). */
export interface HeldPosition {
  symbol: string;
  qty: number;
  /** Paper (ADR 072): another trader's row is left out of your cards and raises its own. */
  owner?: Owner;
  /** The retired bot, on an Earlier bots' row. */
  bot?: string | null;
}

export interface CloseReminder {
  symbol: string;
  /** Signed: negative is short. */
  qty: number;
  venue: CloseReminderVenue;
  stage: CloseReminderStage;
  /** An `others` card: whose shares they are. */
  owner?: Owner;
  bot?: string | null;
  /** The rows are last-known (the Gateway dropped on Live). */
  stale: boolean;
  /** When this card was raised or escalated (ms). */
  at: number;
}

/* ---------- Eastern clock ---------- */

export interface EtClock {
  /** YYYY-MM-DD in New York. */
  date: string;
  /** Minutes after midnight in New York. */
  minutes: number;
  /** 0 = Sunday .. 6 = Saturday, in New York. */
  weekday: number;
}

const ET_FORMAT = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York',
  hour12: false,
  weekday: 'short',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
});
const WEEKDAYS: Record<string, number> = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };

export function etClock(now: Date): EtClock {
  const p: Record<string, string> = {};
  for (const part of ET_FORMAT.formatToParts(now)) p[part.type] = part.value;
  const hour = Number(p.hour) % 24; // some engines print midnight as "24"
  return {
    date: `${p.year}-${p.month}-${p.day}`,
    minutes: hour * 60 + Number(p.minute),
    weekday: WEEKDAYS[p.weekday] ?? 0,
  };
}

/** The stage due at this ET minute, or null (before 15:50, or 16:00 and later). */
export function stageAt(minutes: number): Exclude<CloseReminderStage, 'others'> | null {
  if (minutes >= CLOSE_REMIND_CLOSE_MIN_ET) return null;
  if (minutes >= CLOSE_REMIND_FINAL_MIN_ET) return 'final';
  if (minutes >= CLOSE_REMIND_WARN_MIN_ET) return 'warn';
  return null;
}

export function isReminderVenue(venue: string | null | undefined): venue is CloseReminderVenue {
  return venue === 'live' || venue === 'paper';
}

type Holder = Pick<CloseReminder, 'owner' | 'bot'>;

interface Held extends Holder {
  symbol: string;
  qty: number;
}

const holderKey = (h: Holder): string => (h.owner ? `${h.owner}${h.bot ? `:${h.bot}` : ''}` : '');

export function fireKey(date: string, venue: CloseReminderVenue, symbol: string, stage: CloseReminderStage,
  holder: Holder = {}): string {
  const who = stage === 'others' ? holderKey(holder) : '';
  return `${date}|${venue}|${symbol}|${stage}${who ? `|${who}` : ''}`;
}

/** One card per stock and book: yours moves from warn to final, each other trader's stands beside it. */
const cardKey = (r: Pick<CloseReminder, 'symbol' | 'stage'> & Holder): string =>
  (r.stage === 'others' ? `others|${holderKey(r)}|${r.symbol}` : r.symbol);

/** True for another trader's row: you never close it, so it never joins your card. */
const othersRow = (p: HeldPosition): boolean => p.owner != null && p.owner !== 'you';

/** Each stock's shares per holder (yours together, each other trader apart), signed, across the rows this keeps. */
function heldBy(positions: readonly HeldPosition[], keep: (p: HeldPosition) => boolean): Map<string, Held> {
  const held = new Map<string, Held>();
  for (const p of positions) {
    const symbol = String(p.symbol ?? '').trim().toUpperCase();
    if (!keep(p) || !symbol || !Number.isFinite(p.qty) || p.qty === 0) continue;
    const holder: Holder = othersRow(p) ? { owner: p.owner, bot: p.owner === 'earlier_bots' ? p.bot ?? null : null } : {};
    const key = `${holderKey(holder)}|${symbol}`;
    held.set(key, { symbol, qty: (held.get(key)?.qty ?? 0) + p.qty, ...holder });
  }
  return held;
}

/* ---------- The pure fold ---------- */

export interface DueInput {
  positions: readonly HeldPosition[];
  venue: string | null | undefined;
  stale: boolean;
  now: Date;
  /** Keys already fired today (a dismissed card stays dismissed at its stage). */
  fired: ReadonlySet<string>;
  current: readonly CloseReminder[];
}

export interface DueResult {
  reminders: readonly CloseReminder[];
  /** Keys this read fires for the first time. */
  newKeys: readonly string[];
  date: string;
}

/** Pure: the cards due now. An unchanged card is returned as the same object. */
export function dueCloseReminders(input: DueInput): DueResult {
  const clock = etClock(input.now);
  const venue = isReminderVenue(input.venue) ? input.venue : null;
  const weekday = clock.weekday >= 1 && clock.weekday <= 5;
  const stage = venue && weekday ? stageAt(clock.minutes) : null;
  if (!venue || !stage) return { reminders: [], newKeys: [], date: clock.date };

  const current = new Map(input.current.map(r => [cardKey(r), r]));
  const reminders: CloseReminder[] = [];
  const newKeys: string[] = [];
  const raise = (held: ReadonlyMap<string, Held>, at: CloseReminderStage) => {
    for (const { symbol, qty, ...holder } of held.values()) {
      if (qty === 0) continue;
      const key = fireKey(clock.date, venue, symbol, at, holder);
      const have = current.get(cardKey({ symbol, stage: at, ...holder }));
      if (input.fired.has(key)) {
        if (!have) continue; // dismissed at this stage: stays dismissed
        reminders.push(
          have.stage === at && have.qty === qty && have.stale === input.stale && have.venue === venue
            ? have
            : { ...have, stage: at, qty, stale: input.stale, venue },
        );
        continue;
      }
      newKeys.push(key);
      reminders.push({ symbol, qty, venue, stage: at, stale: input.stale, at: input.now.getTime(), ...holder });
    }
  };
  raise(heldBy(input.positions, p => !othersRow(p)), stage);
  if (venue === 'paper' && clock.minutes >= CLOSE_REMIND_OTHERS_MIN_ET) {
    raise(heldBy(input.positions, othersRow), 'others');
  }
  reminders.sort((a, b) => a.symbol.localeCompare(b.symbol));
  return { reminders, newKeys, date: clock.date };
}

/* ---------- The store ---------- */

interface FiredPref {
  schema_version: number;
  date: string;
  keys: string[];
}

function parseFired(raw: unknown): FiredPref | null {
  if (!raw || typeof raw !== 'object') return null;
  const r = raw as Partial<FiredPref>;
  if (r.schema_version !== CLOSE_REMIND_FIRED_SCHEMA_VERSION || typeof r.date !== 'string' || !Array.isArray(r.keys)) return null;
  return { schema_version: r.schema_version, date: r.date, keys: r.keys.filter((k): k is string => typeof k === 'string') };
}

let reminders: readonly CloseReminder[] = [];
let fired: { date: string; keys: Set<string> } | null = null;
const listeners = new Set<() => void>();

function publish(next: readonly CloseReminder[]): void {
  reminders = next;
  listeners.forEach(fn => fn());
}

function firedToday(date: string): Set<string> {
  if (fired && fired.date === date) return fired.keys;
  const stored = readPref<FiredPref | null>(CLOSE_REMIND_FIRED_PREF_KEY, null, parseFired);
  fired = { date, keys: new Set(stored && stored.date === date ? stored.keys : []) };
  return fired.keys;
}

function sameCards(a: readonly CloseReminder[], b: readonly CloseReminder[]): boolean {
  return a.length === b.length && a.every((r, i) => r === b[i]);
}

/** A tick: the positions and venue as the desk holds them now. Raises, escalates, retires cards. */
export function noteCloseReminders(
  positions: readonly HeldPosition[],
  venue: string | null | undefined,
  stale: boolean,
  now: Date = new Date(),
): void {
  const date = etClock(now).date;
  const keys = firedToday(date);
  const res = dueCloseReminders({ positions, venue, stale, now, fired: keys, current: reminders });
  if (res.newKeys.length) {
    res.newKeys.forEach(k => keys.add(k));
    writePref(CLOSE_REMIND_FIRED_PREF_KEY, { schema_version: CLOSE_REMIND_FIRED_SCHEMA_VERSION, date, keys: [...keys] });
  }
  if (!sameCards(res.reminders, reminders)) publish(res.reminders);
}

/** `stage`: which of the stock's cards, yours (the default) or another trader's (`holder` says whose). */
export function dismissCloseReminder(symbol: string, stage?: CloseReminderStage, holder: Holder = {}): void {
  const gone = cardKey({ symbol, stage: stage ?? 'final', ...holder });
  const next = reminders.filter(r => cardKey(r) !== gone);
  if (next.length !== reminders.length) publish(next);
}

export function getCloseReminders(): readonly CloseReminder[] {
  return reminders;
}

export function subscribeCloseReminders(fn: () => void): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

/** Test-only: forgets the cards and today's fired keys. */
export function resetCloseRemindersForTests(): void {
  fired = null;
  try {
    localStorage.removeItem(CLOSE_REMIND_FIRED_PREF_KEY);
  } catch {
    // no storage in this environment
  }
  publish([]);
}
