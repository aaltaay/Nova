/**
 * Who sent an order: the Orders table's "Sent by" column (operator report 2026-10-01: "I don't
 * remember selling it" -- the bot trip sold 100 ACN on Paper and the row read like any other
 * market sell).
 *
 * Read from the row's own stamps, never inferred from its side, price or time:
 * - `order_origin`: which part of Nova sent it (the backend's `EXECUTION_ORIGINS`);
 * - `order_source`: the ADR 007 command source, for rows placed before origins were recorded;
 * - `source: 'ib_recovered'`: IBKR knows the order and Nova never placed it.
 * A row with none of them says so rather than guessing "You".
 */
import type { IbkrOrder } from './types';

/** `breaker`: a loss breaker or KILL sold for you -- the rows to notice. */
export type SentByTone = 'you' | 'nova' | 'breaker' | 'outside' | 'unknown';

export type SentBy = { label: string; tip: string; tone: SentByTone };

export const SENT_BY_TITLE = 'Sent by';

const BY_ORIGIN: Record<string, SentBy> = {
  ticket_flatten: {
    label: 'You · Flatten',
    tone: 'you',
    tip: "You: the ticket's Flatten, the quick bar's Flatten or a Flatten hotkey.",
  },
  emergency_kill: {
    label: 'KILL',
    tone: 'breaker',
    tip: "The header's Emergency KILL: it cancelled every working order and sold every position.",
  },
  bot_trip: {
    label: 'Bot trip',
    tone: 'breaker',
    tip:
      "The bot trip: the day's P&L reached your bot trip limit, so Nova sold every position and " +
      'turned the bot Off. You set the limit on the Bots page.',
  },
  all_stop: {
    label: 'All-stop',
    tone: 'breaker',
    tip:
      "The all-stop: the day's P&L reached your all-stop limit, so Nova sold every position and " +
      'locked buys until 04:00 ET. You set the limit on the Bots page.',
  },
  bot: {
    label: 'Bot',
    tone: 'nova',
    tip: "Nova's bot: its entry, a resting exit, its time stop or flush exit, or its last-resort close.",
  },
  auto_entry: {
    label: 'Auto-entry',
    tone: 'nova',
    tip: "Auto-entry: Nova bought at the setup's trigger. Selling it is yours.",
  },
  approve: {
    label: 'Approve',
    tone: 'nova',
    tip: 'Approve: you approved the plan, and Nova sent it at the trigger.',
  },
  bot_api: {
    label: 'Bot API',
    tone: 'nova',
    tip: "A bot through Nova's localhost bot API.",
  },
};

const BY_SOURCE: Record<string, SentBy> = {
  manual: {
    label: 'You',
    tone: 'you',
    tip: 'You: the order ticket, a hotkey or a chart action.',
  },
  bot: {
    label: 'Bot',
    tone: 'nova',
    tip: 'A bot. It was placed before Nova recorded which bot sent an order.',
  },
  flatten: {
    label: 'Flatten',
    tone: 'unknown',
    tip:
      "A flatten: your Flatten, the header's KILL, a loss breaker (bot trip or all-stop) or the " +
      "bot's last-resort close. It was placed before Nova recorded which one; newer orders say.",
  },
  benchmark: {
    label: 'Benchmark',
    tone: 'nova',
    tip: "Nova's execution benchmark.",
  },
};

const OUTSIDE: SentBy = {
  label: 'Outside Nova',
  tone: 'outside',
  tip: 'Placed outside Nova (TWS, IBKR Mobile or another API client): IBKR knows it, Nova never sent it.',
};

const NOT_RECORDED: SentBy = {
  label: '—',
  tone: 'unknown',
  tip:
    'Not recorded on this row. A Live order shows who sent it once it closes. An order from ' +
    'before Nova recorded senders has none.',
};

export function orderSentBy(order: Pick<IbkrOrder, 'source' | 'order_source' | 'order_origin'>): SentBy {
  if (order.source === 'ib_recovered') return OUTSIDE;
  const origin = (order.order_origin ?? '').trim();
  if (origin) {
    return BY_ORIGIN[origin] ?? {
      label: origin,
      tone: 'unknown',
      tip: `Sent by "${origin}", a sender this desk does not know yet. Reload the desk after an update.`,
    };
  }
  const source = (order.order_source ?? '').trim();
  if (source) {
    return BY_SOURCE[source] ?? { label: source, tone: 'unknown', tip: `Order source "${source}".` };
  }
  return NOT_RECORDED;
}
