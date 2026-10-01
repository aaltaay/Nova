/**
 * The loss breakers' notice (operator report 2026-10-01: "Could you see who sold here? I don't
 * remember selling it."). The bot trip sold 100 ACN on Paper at 09:43 and said so only on the
 * Bots and Account pages. Now it is one of the bot's notices (`botNoticeStore`), in every
 * window of the desk, and it stays until dismissed.
 *
 * The source is the bot audit stream the desk already polls (`botSessionPoller`): every trip
 * writes one `breaker_soft` (bot trip) or `breaker_hard` (all-stop) line with the day's P&L,
 * the limit, the venue and, since 2026-10-01, `closes` -- what the flatten sold. A line is
 * announced once per window, while it is younger than `BREAKER_NOTICE_MAX_AGE_SEC`: a desk
 * opened right after a trip still hears of it, and an old trip is never news.
 */
import { formatMoney } from '../utils/formatMoney';
import { formatShareQty } from '../utils/formatShareQty';
import type { BotNoticeTone } from './botNoticeStore';
import { etClock } from './botsPageFormat';
import type { BotAuditEntry } from './types';

/** A trip older than this is not announced (the Bots page and the Orders table still say it). */
export const BREAKER_NOTICE_MAX_AGE_SEC = 600;

const KINDS: Record<string, BreakerKind> = { breaker_soft: 'bot_trip', breaker_hard: 'all_stop' };
const NAMES: Record<BreakerKind, string> = { bot_trip: 'Bot trip', all_stop: 'All-stop' };
const VENUES: Record<string, string> = { live: 'Live', paper: 'Paper', sim: 'Sim' };

export type BreakerKind = 'bot_trip' | 'all_stop';

export type BreakerClose = {
  symbol: string;
  side: string | null;
  qty: number | null;
  ok: boolean;
  orderId: number | null;
  error: string | null;
};

export type BreakerTrip = {
  id: string;
  kind: BreakerKind;
  /** Epoch seconds of the trip. */
  at: number;
  venue: string | null;
  pnl: number | null;
  threshold: number | null;
  /** What the flatten sold; null when the backend did not say (older than 2026-10-01). */
  closes: BreakerClose[] | null;
  /** False: the flatten failed and positions may still be open. Null: unknown. */
  flattenOk: boolean | null;
  flattenError: string | null;
};

function num(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function text(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

function parseCloses(value: unknown): BreakerClose[] | null {
  if (!Array.isArray(value)) return null;
  return value
    .filter((row): row is Record<string, unknown> => Boolean(row) && typeof row === 'object')
    .map((row) => ({
      symbol: String(row.symbol ?? '').toUpperCase(),
      side: text(row.side),
      qty: num(row.qty),
      ok: row.ok === true,
      orderId: num(row.order_id),
      error: text(row.error),
    }));
}

/** One audit line as a trip; null for any line that is not a breaker trip. */
export function breakerTripOf(entry: BotAuditEntry): BreakerTrip | null {
  const kind = KINDS[entry.action];
  if (!kind || !Number.isFinite(entry.timestamp)) return null;
  const inputs = entry.inputs ?? {};
  return {
    id: `${entry.action}:${entry.timestamp}`,
    kind,
    at: entry.timestamp,
    venue: text(inputs.venue) ?? text(entry.venue),
    pnl: num(inputs.pnl),
    threshold: num(inputs.threshold),
    closes: parseCloses(inputs.closes),
    flattenOk: typeof inputs.flatten_ok === 'boolean' ? inputs.flatten_ok : null,
    flattenError: text(inputs.flatten_error),
  };
}

/** The trips in `audit` not yet in `seen` and young enough to announce, oldest first; marks them seen. */
export function takeNewBreakerTrips(
  audit: readonly BotAuditEntry[],
  seen: Set<string>,
  nowSec: number,
): BreakerTrip[] {
  const fresh: BreakerTrip[] = [];
  for (const entry of audit) {
    const trip = breakerTripOf(entry);
    if (!trip || seen.has(trip.id)) continue;
    seen.add(trip.id);
    if (nowSec - trip.at <= BREAKER_NOTICE_MAX_AGE_SEC) fresh.push(trip);
  }
  return fresh.sort((a, b) => a.at - b.at);
}

export function breakerTripTitle(trip: BreakerTrip): string {
  if (trip.flattenOk === false) return `${NAMES[trip.kind]}: the sell failed — close your positions yourself`;
  return `${NAMES[trip.kind]} sold your positions`;
}

/** "Sold 100 ACN · order 68", or why a position was not sold. */
export function breakerCloseLine(close: BreakerClose): string {
  const qty = close.qty != null ? `${formatShareQty(close.qty)} ` : '';
  if (!close.ok) return `${qty}${close.symbol} was not sold — ${close.error ?? 'the close was refused'}`;
  const verb = close.side === 'BUY' ? 'Bought back' : 'Sold';
  return `${verb} ${qty}${close.symbol}${close.orderId != null ? ` · order ${close.orderId}` : ''}`;
}

/** The notice's lines: what tripped and when, what was sold, and what follows. */
export function breakerTripBody(trip: BreakerTrip): string {
  const facts: string[] = [];
  if (trip.venue) facts.push(VENUES[trip.venue] ?? trip.venue);
  if (trip.pnl != null && trip.threshold != null) {
    facts.push(`day P&L ${formatMoney(trip.pnl)} reached your ${formatMoney(trip.threshold)} limit`);
  } else if (trip.pnl != null) {
    facts.push(`day P&L ${formatMoney(trip.pnl)}`);
  }
  const clock = etClock(trip.at);
  if (clock) facts.push(`${clock} ET`);
  const lines = [facts.join(' · ')];
  if (trip.closes == null) lines.push('Every open position was sold. The Orders table lists them.');
  else if (!trip.closes.length) lines.push('Nothing was held, so nothing was sold.');
  else lines.push(...trip.closes.map(breakerCloseLine));
  if (trip.flattenOk === false && trip.flattenError) lines.push(trip.flattenError);
  if (trip.kind === 'all_stop') {
    const venue = trip.venue ? VENUES[trip.venue] ?? trip.venue : 'this venue';
    lines.push(`Buys on ${venue} are locked until 04:00 ET. You set the limit on the Bots page.`);
  } else {
    lines.push('The bot is Off until 04:00 ET or until you turn it back on. You set the limit on the Bots page.');
  }
  return lines.filter(Boolean).join('\n');
}

export type BreakerNoticePush = (notice: { tone: BotNoticeTone; title: string; text: string }) => unknown;

/** This window's trips already announced: one notice per trip, whatever remounts. */
const seenTrips = new Set<string>();

/** Read one audit snapshot and raise a notice for each trip this window has not announced. */
export function noteBreakerTrips(
  audit: readonly BotAuditEntry[],
  push: BreakerNoticePush,
  nowSec = Date.now() / 1000,
): number {
  const fresh = takeNewBreakerTrips(audit, seenTrips, nowSec);
  for (const trip of fresh) {
    // 'bad' stays until dismissed: a breaker selling for you is never a passing toast.
    push({ tone: 'bad', title: breakerTripTitle(trip), text: breakerTripBody(trip) });
  }
  return fresh.length;
}

export function resetBreakerTripsForTests(): void {
  seenTrips.clear();
}
