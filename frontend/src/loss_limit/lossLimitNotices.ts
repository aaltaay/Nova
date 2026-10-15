/**
 * The daily loss limit's notices (ADR 056), pure: from one `GET /api/loss-limit` answer, the warnings (80% of
 * the limit, with Warn me) and the trips (the limit) this window has not announced yet, in words and as voice
 * lines. They replace the bot trip's and the all-stop's notices.
 *
 * Each warning and each trip is announced once per window, while it is younger than
 * `LOSS_LIMIT_NOTICE_MAX_AGE_SEC`: a desk opened right after a trip still hears of it, and an old one is never
 * news. A warning the same account has already tripped past is not said: the trip says more. A trip stays on
 * screen until dismissed; a warning leaves on its own. A trip whose Auto sell is still selling (`sell: "pending"`)
 * waits, unseen, for its answer -- up to `LOSS_LIMIT_SELL_WAIT_SEC` -- so the notice can say what was sold.
 */
import { formatMoney } from '../utils/formatMoney';
import { formatShareQty } from '../utils/formatShareQty';
import type { LossLimitAccount, LossLimitClose, LossLimitView } from './lossLimitApi';
import {
  LOSS_LIMIT_NOT_SOLD_UNKNOWN,
  LOSS_LIMIT_STILL_SELLING,
  LOSS_LIMIT_TRIP_TITLE,
  LOSS_LIMIT_WARN_TITLE,
  lossLimitNotSoldLine,
  lossLimitSoldLine,
  lossLimitTripLine,
  lossLimitTripSpoken,
  lossLimitWarnBody,
  lossLimitWarnSpoken,
} from './lossLimitNoticeWords';
import { LOSS_LIMIT_NOTICE_MAX_AGE_SEC, LOSS_LIMIT_SELL_WAIT_SEC } from './lossLimitWords';

const ACCOUNT_NAMES: Record<string, string> = { live: 'Live', paper: 'Paper', sim: 'Sim' };
const ACCOUNT_ORDER = ['live', 'paper', 'sim'];

export type LossLimitEventKind = 'warn' | 'trip';

export interface LossLimitEvent {
  /** One per account, kind and moment: a limit changed and crossed again is a new event. */
  id: string;
  kind: LossLimitEventKind;
  account: string;
  /** Epoch seconds of the warning or the trip. */
  at: number;
  name: string;
  loss: number | null;
  limit: number | null;
  sold: LossLimitClose[] | null;
  sellError: string | null;
  noNewBuys: string | null;
  /** Auto sell has not answered yet. */
  selling: boolean;
}

export interface LossLimitNotice {
  tone: 'warn' | 'bad';
  title: string;
  text: string;
}

export type LossLimitNoticePush = (notice: LossLimitNotice) => unknown;
export type LossLimitSpeak = (line: string) => unknown;

function num(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function text(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim().replace(/ -- /g, ' — ') : null;
}

/** "$1,620": whole dollars, as the limit is set. */
function dollars(value: number | null): string {
  return value == null ? 'an unknown amount' : formatMoney(value, 0);
}

/** "1,620" for the voice; it says the word "dollars" itself. */
function spokenDollars(value: number | null): string {
  return value == null ? 'an unknown number of' : Math.round(value).toLocaleString('en-US');
}

/** "10:12 ET"; empty when unknown. */
function etClock(epochSec: number): string {
  if (!Number.isFinite(epochSec) || epochSec <= 0) return '';
  const t = new Date(epochSec * 1000).toLocaleTimeString('en-US', {
    timeZone: 'America/New_York', hour12: false, hour: '2-digit', minute: '2-digit',
  });
  return `${t} ET`;
}

function eventsOf(view: LossLimitView): LossLimitEvent[] {
  const out: LossLimitEvent[] = [];
  const day = view.day ?? '';
  const settingsLimit = num(view.settings?.limit_usd);
  const accounts = view.accounts ?? {};
  const ids = [...ACCOUNT_ORDER, ...Object.keys(accounts).filter(id => !ACCOUNT_ORDER.includes(id))];
  for (const id of ids) {
    const row = (accounts as Record<string, LossLimitAccount | undefined>)[id];
    if (!row || typeof row !== 'object') continue;
    const name = text(row.name) ?? ACCOUNT_NAMES[id] ?? id;
    const warnedAt = num(row.warned_at);
    const trippedAt = num(row.tripped_at);
    const base = { account: id, name, sold: null, sellError: null, noNewBuys: null, selling: false };
    if (trippedAt != null) {
      out.push({
        ...base,
        id: `${day}:${id}:trip:${trippedAt}`,
        kind: 'trip',
        at: trippedAt,
        loss: num(row.tripped_loss),
        limit: num(row.limit_usd) ?? settingsLimit,
        sold: Array.isArray(row.sold) ? row.sold.filter(c => c && typeof c === 'object') : null,
        sellError: text(row.sell_error),
        noNewBuys: text(row.no_new_buys?.text),
        selling: row.sell === 'pending',
      });
    }
    if (warnedAt != null) {
      out.push({
        ...base,
        id: `${day}:${id}:warn:${warnedAt}`,
        kind: 'warn',
        at: warnedAt,
        loss: num(row.warned_loss),
        limit: settingsLimit,
      });
    }
  }
  return out;
}

/** The events in `view` not yet in `seen` and young enough to announce, oldest first; marks every one seen. */
export function takeNewLossLimitEvents(view: LossLimitView, seen: Set<string>, nowSec: number): LossLimitEvent[] {
  const all = eventsOf(view);
  const tripped = new Map(all.filter(e => e.kind === 'trip').map(e => [e.account, e.at]));
  const fresh: LossLimitEvent[] = [];
  for (const event of all) {
    if (seen.has(event.id)) continue;
    // Auto sell still selling: leave the trip unseen so a later answer, with what was sold, is the one said.
    if (event.selling && nowSec - event.at < LOSS_LIMIT_SELL_WAIT_SEC) continue;
    seen.add(event.id);
    if (nowSec - event.at > LOSS_LIMIT_NOTICE_MAX_AGE_SEC) continue;
    const tripAt = tripped.get(event.account);
    if (event.kind === 'warn' && tripAt != null && tripAt >= event.at) continue; // the trip says it
    fresh.push(event);
  }
  return fresh.sort((a, b) => a.at - b.at);
}

/** "Sold 1,000 WETO · order 259", or why a position was not sold. */
export function lossLimitCloseLine(close: LossLimitClose): string {
  const symbol = String(close.symbol ?? '').toUpperCase();
  const qty = num(close.qty) != null ? `${formatShareQty(close.qty)} ` : '';
  if (!close.ok) return lossLimitNotSoldLine(qty, symbol, text(close.error) ?? LOSS_LIMIT_NOT_SOLD_UNKNOWN);
  const verb = String(close.side ?? '').toUpperCase() === 'BUY' ? 'Bought back' : 'Sold';
  return lossLimitSoldLine(verb, qty, symbol, num(close.order_id));
}

/** One event as a notice: a warning in one line; a trip with what holds now and what was sold. */
export function lossLimitNotice(event: LossLimitEvent): LossLimitNotice {
  if (event.kind === 'warn') {
    return { tone: 'warn', title: LOSS_LIMIT_WARN_TITLE,
      text: lossLimitWarnBody(event.name, dollars(event.loss), dollars(event.limit)) };
  }
  const lines = [lossLimitTripLine(event.name, dollars(event.loss), dollars(event.limit), etClock(event.at))];
  if (event.noNewBuys) lines.push(event.noNewBuys);
  for (const close of event.sold ?? []) lines.push(lossLimitCloseLine(close));
  if (event.sellError && !event.sold?.length) lines.push(event.sellError);
  if (event.selling) lines.push(LOSS_LIMIT_STILL_SELLING);
  // A trip stays until dismissed: Nova acting on the account is never a passing toast.
  return { tone: 'bad', title: LOSS_LIMIT_TRIP_TITLE, text: lines.join('\n') };
}

/** One event as the desk's voice line. */
export function lossLimitSpoken(event: LossLimitEvent): string {
  return event.kind === 'warn'
    ? lossLimitWarnSpoken(event.name, spokenDollars(event.loss), spokenDollars(event.limit))
    : lossLimitTripSpoken(event.name);
}

/** This window's events already announced: one notice per event, whatever remounts. */
const seenEvents = new Set<string>();

/**
 * Read one answer: raise a notice for each event this window has not announced, and -- when `speak` is given
 * (the window that reads for every window) -- say it.
 */
export function noteLossLimit(
  view: LossLimitView,
  push: LossLimitNoticePush,
  speak: LossLimitSpeak | null,
  nowSec = Date.now() / 1000,
): number {
  const fresh = takeNewLossLimitEvents(view, seenEvents, nowSec);
  for (const event of fresh) {
    push(lossLimitNotice(event));
    speak?.(lossLimitSpoken(event));
  }
  return fresh.length;
}

export function resetLossLimitNoticesForTests(): void {
  seenEvents.clear();
}
