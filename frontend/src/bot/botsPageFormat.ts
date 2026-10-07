/**
 * Pure helpers for the Bots page (ADR 027, ADR 042, ADR 044): the venue's name, why the Bot was turned
 * off, the bot's trade in one line, and the page's number formats. Gate words are bot/botGateWords.ts;
 * the Bot switch is bot/botSwitch.ts.
 */
import { BOTS_VENUE_NAMES } from '../constantGroups/bots_page';
import { isShortSetup } from '../constantGroups/short_setups';
import { setupLabelOf, strategySetups } from './botLevels';
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
const SHORT_EXIT_WORDS: Record<string, string> = {
  target: 'covered at the target',
  stop: 'stopped out over the buy stop',
  flush: 'covered on a burst of buying',
  outside: 'covered outside the bot',
};

/** The side a bot trade entered (ADR 049, #778 step 5), always in words beside its arrow. */
export function tradeSideTag(trade: Pick<BotTrade, 'side'>): string {
  return trade.side === 'short' ? '▼ short' : '▲ long';
}

/** What the bot trades next (ADR 049, #778 step 5): the first GO trigger among the strategies at On, each with
 * its side. Null while a trade is live (one trade at a time) or the Bot is off. */
export function nextTradeLine(session: BotSession, on: boolean): string | null {
  const live = session.trade && ['entering', 'open', 'exiting'].includes(session.trade.state);
  if (!on || live) return null;
  const ids = strategySetups(session);
  if (!ids.length) return 'Next: nothing — no strategy is On.';
  const names = ids.map(id => {
    const info = (session.setups ?? []).find(s => s.id === id);
    const side = info?.side ?? (isShortSetup(id) ? 'short' : 'long');
    return `${setupLabelOf(id).toLowerCase()} ${tradeSideTag({ side })}`;
  });
  return `Next: the first GO trigger of ${names.join(', ')}, on a stock whose Entry is Bot.`;
}

/** The bot's trade in one line, naming its setup (ADR 030, ADR 042 I); empty when it has none. */
export function tradeLine(trade: BotTrade | null | undefined): string {
  if (!trade) return '';
  const short = trade.side === 'short';
  const sym = `${trade.symbol} ${tradeSideTag(trade)}`;
  const what = trade.setup_type ? ` (${setupLabelOf(trade.setup_type).toLowerCase()})` : '';
  const qty = trade.qty;
  switch (trade.state) {
    case 'entering': {
      const ssr = short && trade.priced_at_ask ? ` (SSR ${trade.ssr ?? 'unknown'}: at the ask)` : '';
      return `${short ? 'Shorting' : 'Buying'} ${sym}${what} · ${qty} at ${px(trade.entry_planned)} limit${ssr}`;
    }
    case 'open':
      return short
        ? `In ${sym}${what} · ${qty} @ ${px(trade.entry_fill_price)} · buy stop ${px(trade.stop)} · cover ${px(trade.target1)}`
        : `In ${sym}${what} · ${qty} @ ${px(trade.entry_fill_price)} · stop ${px(trade.stop)} · target ${px(trade.target1)}`;
    case 'exiting': {
      const stop = short ? 'the buy stop printed' : 'the stop printed';
      const flush = short ? 'a burst of buying' : 'a flush';
      return `${short ? 'Covering' : 'Closing'} ${sym}${what} · ${trade.exit_why === 'stop' ? stop : trade.exit_why === 'flush' ? flush : 'time stop'}`;
    }
    case 'missed':
      return `Missed ${sym}${what} · ${prose(trade.note ?? 'the entry did not fill')}`;
    case 'closed': {
      const why = (short ? SHORT_EXIT_WORDS[trade.exit_reason ?? ''] : null) ?? EXIT_WORDS[trade.exit_reason ?? '']
        ?? trade.exit_reason ?? 'closed';
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
