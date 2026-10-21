/**
 * The daily loss limit's notices (ADR 056, ADR 061), pure: from one `GET /api/loss-limit` answer, the warnings
 * (80% of a line, with Warn me) and the trips (the line) this window has not announced yet, in words and as voice
 * lines, each naming its line -- the account's, your trades' or the bots'. They replace the bot trip's and the
 * all-stop's notices.
 *
 * Each warning and each trip is announced once per window, while it is younger than
 * `LOSS_LIMIT_NOTICE_MAX_AGE_SEC`: a desk opened right after a trip still hears of it, and an old one is never
 * news. A warning the same line has already tripped past is not said: the trip says more. A trip stays on
 * screen until dismissed; a warning leaves on its own. A trip whose Auto sell is still selling (`sell: "pending"`)
 * waits, unseen, for its answer -- up to `LOSS_LIMIT_SELL_WAIT_SEC` -- so the notice can say what was sold.
 */
import { formatMoney } from '../utils/formatMoney';
import { formatShareQty } from '../utils/formatShareQty';
import type {
  LossLimitAccount,
  LossLimitClose,
  LossLimitLineId,
  LossLimitSettings,
  LossLimitView,
} from './lossLimitApi';
import {
  LOSS_LIMIT_NOT_SOLD_UNKNOWN,
  LOSS_LIMIT_STILL_SELLING,
  lossLimitNotSoldLine,
  lossLimitSoldLine,
  lossLimitTripLine,
  lossLimitTripSpoken,
  lossLimitTripTitle,
  lossLimitWarnBody,
  lossLimitWarnSpoken,
  lossLimitWarnTitle,
} from './lossLimitNoticeWords';
import { LOSS_LIMIT_NOTICE_MAX_AGE_SEC, LOSS_LIMIT_SELL_WAIT_SEC } from './lossLimitWords';

const ACCOUNT_NAMES: Record<string, string> = { live: 'Live', paper: 'Paper', sim: 'Sim' };
const ACCOUNT_ORDER = ['live', 'paper', 'sim'];

export type LossLimitEventKind = 'warn' | 'trip';

export interface LossLimitEvent {
  /** One per account, line, kind and moment: a limit changed and crossed again is a new event. */
  id: string;
  kind: LossLimitEventKind;
  account: string;
  line: LossLimitLineId;
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

const LINE_ORDER: LossLimitLineId[] = ['account', 'you', 'bots'];
const SETTING_KEY: Record<LossLimitLineId, keyof LossLimitSettings> = {
  account: 'limit_usd', you: 'you_usd', bots: 'bots_usd',
};

function eventsOf(view: LossLimitView): LossLimitEvent[] {
  const out: LossLimitEvent[] = [];
  const day = view.day ?? '';
  const accounts = view.accounts ?? {};
  const ids = [...ACCOUNT_ORDER, ...Object.keys(accounts).filter(id => !ACCOUNT_ORDER.includes(id))];
  for (const id of ids) {
    const row = (accounts as Record<string, LossLimitAccount | undefined>)[id];
    if (!row || typeof row !== 'object') continue;
    const name = text(row.name) ?? ACCOUNT_NAMES[id] ?? id;
    for (const line of LINE_ORDER) {
      const rec = row.lines?.[line];
      if (!rec || typeof rec !== 'object') continue;
      const settingsLimit = num(view.settings?.[SETTING_KEY[line]]);
      const warnedAt = num(rec.warned_at);
      const trippedAt = num(rec.tripped_at);
      const base = { account: id, line, name, sold: null, sellError: null, noNewBuys: null, selling: false };
      if (trippedAt != null) {
        out.push({
          ...base,
          id: `${day}:${id}:${line}:trip:${trippedAt}`,
          kind: 'trip',
          at: trippedAt,
          loss: num(rec.tripped_loss),
          limit: num(rec.limit_usd) ?? settingsLimit,
          sold: Array.isArray(rec.sold) ? rec.sold.filter(c => c && typeof c === 'object') : null,
          sellError: text(rec.sell_error),
          noNewBuys: text(rec.no_new_buys?.text),
          selling: rec.sell === 'pending',
        });
      }
      if (warnedAt != null) {
        out.push({
          ...base,
          id: `${day}:${id}:${line}:warn:${warnedAt}`,
          kind: 'warn',
          at: warnedAt,
          loss: num(rec.warned_loss),
          limit: num(rec.limit_usd) ?? settingsLimit,
        });
      }
    }
  }
  return out;
}

/** The events in `view` not yet in `seen` and young enough to announce, oldest first; marks every one seen. */
export function takeNewLossLimitEvents(view: LossLimitView, seen: Set<string>, nowSec: number): LossLimitEvent[] {
  const all = eventsOf(view);
  const tripped = new Map(all.filter(e => e.kind === 'trip').map(e => [`${e.account}:${e.line}`, e.at]));
  const fresh: LossLimitEvent[] = [];
  for (const event of all) {
    if (seen.has(event.id)) continue;
    // Auto sell still selling: leave the trip unseen so a later answer, with what was sold, is the one said.
    if (event.selling && nowSec - event.at < LOSS_LIMIT_SELL_WAIT_SEC) continue;
    seen.add(event.id);
    if (nowSec - event.at > LOSS_LIMIT_NOTICE_MAX_AGE_SEC) continue;
    const tripAt = tripped.get(`${event.account}:${event.line}`);
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
    return { tone: 'warn', title: lossLimitWarnTitle(event.line),
      text: lossLimitWarnBody(event.line, event.name, dollars(event.loss), dollars(event.limit)) };
  }
  const lines = [lossLimitTripLine(event.line, event.name, dollars(event.loss), dollars(event.limit), etClock(event.at))];
  if (event.noNewBuys) lines.push(event.noNewBuys);
  for (const close of event.sold ?? []) lines.push(lossLimitCloseLine(close));
  if (event.sellError && !event.sold?.length) lines.push(event.sellError);
  if (event.selling) lines.push(LOSS_LIMIT_STILL_SELLING);
  // A trip stays until dismissed: Nova acting on the account is never a passing toast.
  return { tone: 'bad', title: lossLimitTripTitle(event.line), text: lines.join('\n') };
}

/** One event as the desk's voice line. */
export function lossLimitSpoken(event: LossLimitEvent): string {
  return event.kind === 'warn'
    ? lossLimitWarnSpoken(event.line, event.name, spokenDollars(event.loss), spokenDollars(event.limit))
    : lossLimitTripSpoken(event.line, event.name);
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
