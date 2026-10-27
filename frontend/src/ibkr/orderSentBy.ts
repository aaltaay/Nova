/**
 * Who sent an order: the Orders table's "Sent by" column (operator report 2026-10-01: "I don't
 * remember selling it" -- one of Nova's old loss rules sold 100 ACN on Paper and the row read like
 * any other market sell).
 *
 * Read from the row's own stamps, never inferred from its side, price or time:
 * - `order_origin`: which part of Nova sent it (the backend's `EXECUTION_ORIGINS`; ADR 048 adds the
 *   day cover and the margin call, ADR 056 the daily loss limit's Auto sell, ADR 061 its You and Bots lines);
 * - `order_source`: the ADR 007 command source, for rows placed before origins were recorded;
 * - `source: 'ib_recovered'`: IBKR knows the order and Nova never placed it.
 * A row with none of them says so rather than guessing "You".
 */
import type { IbkrOrder } from './types';

/** `breaker`: Nova sold or covered for you (KILL, the daily loss limit, the day cover, a margin call) -- the rows to notice. */
/** `claude`: Claude's seat (ADR 068), drawn as its violet badge. */
export type SentByTone = 'you' | 'nova' | 'breaker' | 'outside' | 'unknown' | 'claude';

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
  loss_limit: {
    label: 'Loss limit',
    tone: 'breaker',
    tip:
      "The daily loss limit's Auto sell: today's loss reached your limit, so Nova sold every position " +
      'opened today, at market. You set the limit in Settings > Loss limits.',
  },
  // ADR 061: a side line sells only its side's shares opened today.
  loss_limit_you: {
    label: 'Loss limit · You',
    tone: 'breaker',
    tip:
      "Your trades' loss limit's Auto sell: the trades you opened today reached your line, so Nova sold your " +
      "shares opened today, at market. The bots' shares were left alone. You set it in Settings > Loss limits.",
  },
  loss_limit_bots: {
    label: 'Loss limit · Bots',
    tone: 'breaker',
    tip:
      "The bots' loss limit's Auto sell: the trades the bots opened today reached their line, so Nova sold the " +
      "bots' shares opened today, at market. Your shares were left alone. You set it in Settings > Loss limits.",
  },
  // Rows from before ADR 056 keep the names of the two loss rules it replaced.
  bot_trip: {
    label: 'Bot trip',
    tone: 'breaker',
    tip:
      "The bot trip, a loss rule retired on 2026-10-15: the day's P&L reached its limit, so Nova sold every " +
      'position and turned the bot Off. The daily loss limit in Settings > Loss limits replaced it.',
  },
  all_stop: {
    label: 'All-stop',
    tone: 'breaker',
    tip:
      "The all-stop, a loss rule retired on 2026-10-15: the day's P&L reached its limit, so Nova sold every " +
      'position and locked buys until 04:00 ET. The daily loss limit in Settings > Loss limits replaced it.',
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
  nova_exit: {
    label: 'Nova exit',
    tone: 'nova',
    tip: 'Nova takes the exit: you bought the shares and handed Nova the sell. Its stop rests here, raised as '
      + '1-minute candles close over round numbers.',
  },
  day_cover: {
    label: 'Day cover',
    tone: 'breaker',
    tip:
      'The day cover: Nova covers every short still open at 15:55 ET (12:55 on an early close), so no ' +
      "short is held overnight. It cancelled the stock's working orders first.",
  },
  live_trader: {
    label: 'Live Trader',
    tone: 'nova',
    tip: "The Live Trader bot (ADR 055): it copied a TraderTV host's position on Paper -- a step when they opened or "
      + 'added, the sale when they closed, went off air, or the sell-all time came.',
  },
  claude: {
    label: 'Claude',
    tone: 'claude',
    tip: "Claude's seat (ADR 068): Paper only. Claude sent it -- an entry with its stop and targets, a stop moved up, "
      + 'a close or a cancel. Click the Claude pill in the header for why.',
  },
  margin_call: {
    label: 'Margin call',
    tone: 'breaker',
    tip:
      "The margin call: the account's equity fell under its maintenance requirement, where IBKR " +
      'liquidates, so Nova closed the position that needed the most margin -- shorts first -- at market.',
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
      "A flatten: your Flatten, the header's KILL, a sell after a daily loss or the bot's last-resort " +
      'close. It was placed before Nova recorded which one; newer orders say.',
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
    "Not recorded: Nova's order log for today has no record of sending this order. It was " +
    'placed outside Nova, on an earlier day (a GTC order), or before senders were recorded -- or ' +
    'the log could not be read.',
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
