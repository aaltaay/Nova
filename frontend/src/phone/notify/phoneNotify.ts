/**
 * The phone's notification settings as the PC keeps them (`GET /api/phone/notify`, ADR 070 amendment
 * 2026-11-18), and the words the screens say about them. Pure.
 *
 * The PC decides what is sent and when: it holds the settings, watches the desk's own events and sends
 * each notification. The phone only shows the settings and asks the PC to change them.
 */

export type HodMomoMode = 'off' | 'stars' | 'all';

export interface NotifySettings {
  schema_version: 1;
  /** HOD Momo alerts: none, your stars only, or every stock. Running Up never notifies. */
  hod_momo: HodMomoMode;
  /** A star's setup arms, comes near its trigger or triggers. */
  setups: boolean;
  /** A stock joins the top of the Gainers board (the hot list's leaders rule). */
  new_leader: boolean;
  /** A fill on the account: yours, Claude's or the brain's. Sent at any time. */
  fills: boolean;
  /** The daily loss limit's warning and its stop. Sent at any time. */
  loss_limit: boolean;
  /** The days market alerts may come: 0 is Monday, 6 is Sunday. */
  days: number[];
  /** The hours market alerts may come, "HH:MM" in New York time. `end` is after `start`. */
  start: string;
  end: string;
}

export interface NotifyLastSent {
  /** Epoch seconds, the PC's clock. */
  at: number;
  title: string;
  ok: boolean;
  error: string | null;
}

export interface NotifyView {
  schema_version: 1;
  /** The PC can send: it has its sending key and something to send with. */
  available: boolean;
  why_unavailable: string | null;
  /** The key a phone subscribes with (the PC's public half), base64url. */
  public_key: string | null;
  settings: NotifySettings;
  /** One short id per subscribed phone: the first 16 hex of the SHA-256 of its push address. */
  device_ids: string[];
  last_sent: NotifyLastSent | null;
}

/** What this phone's own switch can say. */
export type ThisPhone =
  /** Subscribed, and the PC knows it. */
  | 'on'
  | 'off'
  /** Android was told "Block" for Nova: only the phone's own settings undo that. */
  | 'blocked'
  /** This browser cannot receive a push (no service worker, or the page is not on https). */
  | 'unsupported'
  /** Not read yet. */
  | 'unknown';

export const NOTIFY_STEP_MIN = 30;
/** The trading day the desk has prices for: 04:00 to 20:00 New York time. */
export const NOTIFY_EARLIEST = '04:00';
export const NOTIFY_LATEST = '20:00';
export const DAY_LETTERS: readonly string[] = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];
export const DAY_NAMES: readonly string[] = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const DAY_SHORT: readonly string[] = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

function minutesOf(hhmm: string): number | null {
  const m = /^(\d{2}):(\d{2})$/.exec(hhmm);
  if (!m) return null;
  const total = Number(m[1]) * 60 + Number(m[2]);
  return Number(m[1]) < 24 && Number(m[2]) < 60 ? total : null;
}

function hhmm(minutes: number): string {
  return `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`;
}

/**
 * One press of a stepper: `which` moved by `dir` half hours. Null when the press cannot move it -- the day's
 * edge, or the other end of the window (the start stays before the end by at least one step).
 */
export function stepHours(
  settings: Pick<NotifySettings, 'start' | 'end'>, which: 'start' | 'end', dir: 1 | -1,
): { start: string; end: string } | null {
  const start = minutesOf(settings.start);
  const end = minutesOf(settings.end);
  const lo = minutesOf(NOTIFY_EARLIEST) as number;
  const hi = minutesOf(NOTIFY_LATEST) as number;
  if (start == null || end == null) return null;
  const next = (which === 'start' ? start : end) + dir * NOTIFY_STEP_MIN;
  if (which === 'start') {
    if (next < lo || next > end - NOTIFY_STEP_MIN) return null;
    return { start: hhmm(next), end: settings.end };
  }
  if (next > hi || next < start + NOTIFY_STEP_MIN) return null;
  return { start: settings.start, end: hhmm(next) };
}

/** Why a stepper cannot move further, for the control that is greyed. */
export function stepWhy(which: 'start' | 'end', dir: 1 | -1): string {
  if (which === 'start') {
    return dir < 0 ? `The desk's day starts at ${NOTIFY_EARLIEST} New York time.` : 'The start stays before the end.';
  }
  return dir > 0 ? `The desk's day ends at ${NOTIFY_LATEST} New York time.` : 'The end stays after the start.';
}

export function toggleDay(days: readonly number[], day: number): number[] {
  const set = new Set(days);
  if (set.has(day)) set.delete(day);
  else set.add(day);
  return [...set].filter((d) => d >= 0 && d <= 6).sort((a, b) => a - b);
}

/** "Mon to Fri", "Every day", "Mon, Wed, Fri", "No day". */
export function daysText(days: readonly number[]): string {
  const sorted = [...new Set(days)].filter((d) => d >= 0 && d <= 6).sort((a, b) => a - b);
  if (!sorted.length) return 'No day';
  if (sorted.length === 7) return 'Every day';
  const run = sorted.every((d, i) => i === 0 || d === sorted[i - 1] + 1);
  if (run && sorted.length > 2) return `${DAY_SHORT[sorted[0]]} to ${DAY_SHORT[sorted[sorted.length - 1]]}`;
  return sorted.map((d) => DAY_SHORT[d]).join(', ');
}

/** Whether any kind of notification is switched on. */
export function anyKindOn(s: NotifySettings): boolean {
  return s.hod_momo !== 'off' || s.setups || s.new_leader || s.fills || s.loss_limit;
}

/**
 * One line for the row that leads to the Notifications screen. `short` is for a line with little room
 * (Scan's HOD Momo list): "On · 07:00 to 11:00".
 */
export function notifySummary(view: NotifyView | null, phone: ThisPhone, form: 'long' | 'short' = 'long'): string {
  if (phone === 'unsupported') return form === 'short' ? 'Off' : 'This browser cannot receive them';
  if (phone === 'blocked') return form === 'short' ? 'Blocked' : 'Blocked in this phone\'s settings';
  if (!view || phone === 'unknown') return '…';
  if (phone !== 'on') return 'Off';
  const s = view.settings;
  if (!anyKindOn(s)) return form === 'short' ? 'On · nothing chosen' : 'On · nothing chosen yet';
  const hours = `${s.start} to ${s.end}`;
  return form === 'short' ? `On · ${hours}` : `On · ${daysText(s.days)} · ${hours}`;
}

const ET_TIME = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });

/** "Last sent 07:43 · GMM hit HOD Momo", or what went wrong with the last one. */
export function lastSentText(last: NotifyLastSent | null): string {
  if (!last) return 'Nothing sent yet';
  const at = ET_TIME.format(new Date(last.at * 1000));
  return last.ok ? `Last sent ${at} · ${last.title}` : `Not delivered ${at} · ${last.error ?? 'no reason given'}`;
}

/** The settings, read off the wire. A shape this page does not know is refused, never guessed at. */
export function parseNotifyView(raw: unknown): NotifyView | null {
  const v = raw as Partial<NotifyView> | null;
  const s = v?.settings as Partial<NotifySettings> | undefined;
  if (!v || v.schema_version !== 1 || !s || s.schema_version !== 1) return null;
  if (s.hod_momo !== 'off' && s.hod_momo !== 'stars' && s.hod_momo !== 'all') return null;
  if (!Array.isArray(s.days) || typeof s.start !== 'string' || typeof s.end !== 'string') return null;
  if (minutesOf(s.start) == null || minutesOf(s.end) == null) return null;
  return {
    schema_version: 1,
    available: v.available === true,
    why_unavailable: typeof v.why_unavailable === 'string' ? v.why_unavailable : null,
    public_key: typeof v.public_key === 'string' && v.public_key ? v.public_key : null,
    settings: {
      schema_version: 1,
      hod_momo: s.hod_momo,
      setups: s.setups === true,
      new_leader: s.new_leader === true,
      fills: s.fills === true,
      loss_limit: s.loss_limit === true,
      days: s.days.filter((d): d is number => Number.isInteger(d) && d >= 0 && d <= 6),
      start: s.start,
      end: s.end,
    },
    device_ids: Array.isArray(v.device_ids) ? v.device_ids.filter((d): d is string => typeof d === 'string') : [],
    last_sent: v.last_sent && typeof v.last_sent === 'object' && typeof v.last_sent.at === 'number'
      ? {
        at: v.last_sent.at,
        title: String(v.last_sent.title ?? ''),
        ok: v.last_sent.ok === true,
        error: typeof v.last_sent.error === 'string' ? v.last_sent.error : null,
      }
      : null,
  };
}
