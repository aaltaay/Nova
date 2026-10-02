/**
 * Pure helpers for the Bots page (ADR 027, ADR 042, ADR 044): the venue's name, why the Bot was turned
 * off, the bot's trade in one line, and the page's number formats. Gate words are bot/botGateWords.ts;
 * the Bot switch is bot/botSwitch.ts.
 */
import { BOTS_VENUE_NAMES } from '../constantGroups/bots_page';
import { setupLabelOf } from './botLevels';
import { etTime } from './botWhen';
import type { BotDeactivated, BotSession, BotTrade } from './types';

/**
 * "Paper" / "Sim" / "Live" for the desk venue the session is the dial of; "this venue" when
 * unknown. The venue gate is the backend's word on the desk venue now; then the venue whose
 * dial the session's fields are (`level_venue`), the sleeve's and the breakers'.
 */
export function sessionVenueName(session: BotSession): string {
  const gate = (session.gates ?? []).find(g => g.id === 'venue');
  const fromGate = typeof gate?.detail?.venue === 'string' ? gate.detail.venue : null;
  const v = fromGate ?? session.level_venue ?? session.caps?.venue ?? session.breakers?.venue ?? '';
  return BOTS_VENUE_NAMES[String(v)] ?? 'this venue';
}

/** Why the backend turned the bot off (ADR 042 B), when the backend sends no words of its own. */
const DEACTIVATED_WORDS: Record<string, string> = {
  restart: 'the backend restarted',
  padlock: 'the padlock was locked',
  venue: 'the desk changed venue',
  level: 'the Bot was switched off',
  no_setup: 'no strategy was left at On',
  bot_trip: 'the bot trip fired',
  all_stop: 'the all-stop fired',
  operator: 'you turned it off',
};

/** "Turned off at 09:41 ET — the backend restarted"; empty when the backend says nothing. */
export function deactivatedLine(d: BotDeactivated | null | undefined): string {
  if (!d) return '';
  const raw = d.text ?? DEACTIVATED_WORDS[d.reason] ?? d.reason.replace(/_/g, ' ');
  const words = prose(raw).replace(/^Not active\s*[—-]+\s*/i, '');
  const at = etTime(d.at);
  return `Turned off${at ? ` at ${at}` : ''} — ${words}`;
}

const EXIT_WORDS: Record<string, string> = {
  target: 'target',
  stop: 'stopped out',
  time: 'time stop',
  flush: 'flush exit',
  outside: 'closed outside the bot',
  handed: 'handed to you',
};

/** The bot's trade in one line, naming its setup (ADR 030, ADR 042 I); empty when it has none. */
export function tradeLine(trade: BotTrade | null | undefined): string {
  if (!trade) return '';
  const sym = trade.symbol;
  const what = trade.setup_type ? ` (${setupLabelOf(trade.setup_type).toLowerCase()})` : '';
  const qty = trade.qty;
  switch (trade.state) {
    case 'entering':
      return `Buying ${sym}${what} · ${qty} at ${px(trade.entry_planned)} limit`;
    case 'open':
      return `In ${sym}${what} · ${qty} @ ${px(trade.entry_fill_price)} · stop ${px(trade.stop)} · target ${px(trade.target1)}`;
    case 'exiting':
      return `Closing ${sym}${what} · ${trade.exit_why === 'stop' ? 'the stop printed' : trade.exit_why === 'flush' ? 'a flush' : 'time stop'}`;
    case 'missed':
      return `Missed ${sym}${what} · ${prose(trade.note ?? 'the entry did not fill')}`;
    case 'closed': {
      const why = EXIT_WORDS[trade.exit_reason ?? ''] ?? trade.exit_reason ?? 'closed';
      return `Last trade ${sym}${what} · ${why}${trade.r != null ? ` · ${fmtR(trade.r)}` : ''}`;
    }
    default:
      return `${sym}${what} · ${trade.state}`;
  }
}

function px(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—';
  return v < 1 ? v.toFixed(4) : v.toFixed(2);
}

/** Whole dollars with a real minus sign: -50 -> "−$50". */
export function fmtUsd(v: number): string {
  return `${v < 0 ? '−' : ''}$${Math.abs(v).toLocaleString('en-US')}`;
}

/** Dollars and cents with a real minus sign: -9.5 -> "−$9.50"; unknown -> "—". */
export function fmtUsdCents(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—';
  const text = Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return `${v < 0 ? '−' : ''}$${text}`;
}

export function fmtR(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—';
  const text = Math.abs(v).toFixed(2);
  return `${v > 0 ? '+' : v < 0 ? '−' : ''}${text}R`;
}

/** Backend prose writes ASCII " -- "; the page sets it as a dash. */
export function prose(text: string | null | undefined): string {
  return (text ?? '').replace(/ -- /g, ' — ');
}

/** Eastern wall-clock time of an epoch second, HH:MM:SS; blank when unknown. */
export function etClock(ts: number | null | undefined): string {
  if (!ts || !Number.isFinite(ts)) return '';
  return new Date(ts * 1000).toLocaleTimeString('en-US', { timeZone: 'America/New_York', hour12: false });
}

/** The setup that names a scoreboard when nothing else says: the first at Strategy, else the first pullback. */
export function setupName(setup: string | null | undefined): string {
  return setupLabelOf(setup || 'first_pullback');
}
