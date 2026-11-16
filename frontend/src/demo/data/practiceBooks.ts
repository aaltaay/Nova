/**
 * The three traders' books in the sample Paper ledger (ADR 072, ADR 043): Nova Marketing Sample Data, read the way
 * the backend reads a ledger -- your manual fills are yours, Claude's are Claude's, and a retired strategy bot's
 * fills are Earlier bots'. The brain has not traded. Every book's figures add up to the account's, to the cent.
 */
import { etMs, r2 } from './market';

export type Book = 'you' | 'claude' | 'brain' | 'earlier_bots';
export const BOOKS: readonly Book[] = ['you', 'claude', 'brain', 'earlier_bots'];
/** The retired strategy bot behind Earlier bots' sample fills (its origin, "Strategy bot"). */
export const EARLIER_BOT = 'bot';
/** That bot's own id on its fills (the strategy it ran). */
const EARLIER_BOT_ID = 'nova-first-pullback';
/** Each AI trader's budget until Settings sets one (ADR 072). */
const TRADER_BUDGET_USD = 25_000;

export interface BookSums {
  realized: number;
  fills: number;
  commissions: number;
  fees: number;
}

export interface BookFill {
  ts: number;
  order_id: number;
  symbol: string;
  side: string;
  qty: number;
  price: number;
  source: string;
  bot_id: string | null;
  commission: number;
  fees: number;
  realized: number;
  fill_estimated: true;
  fill_basis: string;
  owner: Book;
  bot: string | null;
  parts: Array<{ owner: Book; bot: string | null; qty: number; closes: boolean; realized: number; commission: number; fees: number }>;
}

/** One fill, wholly one book's: its order's own stamps say whose. */
export function bookFill(
  ts: number, order_id: number, symbol: string, side: string, qty: number, price: number, owner: Book,
  commission: number, fees: number, realized: number,
): BookFill {
  const bot = owner === 'earlier_bots' ? EARLIER_BOT : null;
  return {
    ts, order_id, symbol, side, qty, price, source: owner === 'you' ? 'manual' : 'bot',
    bot_id: owner === 'earlier_bots' ? EARLIER_BOT_ID : null,
    commission, fees, realized, fill_estimated: true, fill_basis: 'quote', owner, bot,
    parts: [{ owner, bot, qty, closes: side === 'SELL', realized, commission, fees }],
  };
}

const at = (h: number, m: number, s = 0) => etMs(h, m, s) / 1000;

/**
 * The sample morning's fills; net realized per fill = gross P&L - its commission - its fees. SMPL is a retired
 * strategy bot's (the morning predates ADR 072, so its fills read as Earlier bots').
 */
export const SAMPLE_FILLS_TODAY: readonly BookFill[] = [
  bookFill(at(7, 58, 12), 7001, 'FLTX', 'BUY', 2000, 0.8, 'you', 2.0, 0, -2.0),
  bookFill(at(8, 6, 40), 7002, 'FLTX', 'SELL', 2000, 0.84, 'you', 2.0, 0.15, 77.85),
  bookFill(at(8, 52, 3), 7003, 'SMPL', 'BUY', 10, 3.8, 'earlier_bots', 1.0, 0, -1.0),
  bookFill(at(9, 3, 31), 7004, 'SMPL', 'SELL', 10, 4.02, 'earlier_bots', 1.0, 0.02, 1.18),
  bookFill(at(9, 20, 8), 7005, 'RUNR', 'BUY', 600, 6.17, 'you', 3.0, 0, -3.0),
  bookFill(at(9, 29, 44), 7006, 'RUNR', 'SELL', 600, 6.74, 'you', 3.0, 0.18, 338.82),
  bookFill(at(9, 37, 15), 7007, 'GAPX', 'BUY', 1250, 1.8872, 'you', 2.5, 0, -2.5),
];

/** Prior days a trader other than you traded: its realized that day (two fills); the rest of the day is yours. */
const PRIOR_SPLIT: Record<string, Partial<Record<Book, number>>> = {
  '2026-09-03': { claude: 23.4 },
  '2026-09-10': { earlier_bots: 18.6 },
  '2026-09-16': { claude: -31.2 },
  '2026-09-22': { claude: 27.15 },
  '2026-09-24': { earlier_bots: -12.4 },
  '2026-09-25': { claude: 19.8, earlier_bots: 6.25 },
};

const sums = (realized: number, fills: number, commissions: number, fees: number): BookSums =>
  ({ realized: r2(realized), fills, commissions: r2(commissions), fees: r2(fees) });
const NONE = sums(0, 0, 0, 0);

/** A daily row's four books and its retired bots: `[date, net realized, fills]` split by PRIOR_SPLIT. */
export function priorBooks(date: string, realized: number, fills: number): Record<Book, BookSums> & { by_bot: Record<string, BookSums> } {
  const split = PRIOR_SPLIT[date] ?? {};
  const others = BOOKS.filter((b) => b !== 'you' && split[b] != null);
  const out: Record<Book, BookSums> = { you: NONE, claude: NONE, brain: NONE, earlier_bots: NONE };
  for (const b of others) out[b] = sums(split[b] as number, 2, 2 * 1.6, 2 * 0.05);
  const yours = fills - 2 * others.length;
  out.you = sums(realized - others.reduce((s, b) => s + (split[b] as number), 0), yours, yours * 1.6, yours * 0.05);
  return { ...out, by_bot: out.earlier_bots.fills ? { [EARLIER_BOT]: out.earlier_bots } : {} };
}

/** Today's row's four books, from the day's own fills. */
export function fillBooks(fills: readonly BookFill[]): Record<Book, BookSums> & { by_bot: Record<string, BookSums> } {
  const out = {} as Record<Book, BookSums>;
  for (const b of BOOKS) {
    const own = fills.filter((f) => f.owner === b);
    out[b] = sums(own.reduce((s, f) => s + f.realized, 0), own.length, own.reduce((s, f) => s + f.commission, 0),
      own.reduce((s, f) => s + f.fees, 0));
  }
  return { ...out, by_bot: out.earlier_bots.fills ? { [EARLIER_BOT]: out.earlier_bots } : {} };
}

/** An equity point's books: each one's running realized (the sample ledger holds no open P&L between fills). */
export function pointBooks(run: Record<Book, number>) {
  return {
    you_pnl: r2(run.you), claude_pnl: r2(run.claude), brain_pnl: r2(run.brain), earlier_bots_pnl: r2(run.earlier_bots),
    you_realized: r2(run.you), claude_realized: r2(run.claude), brain_realized: r2(run.brain),
    earlier_bots_realized: r2(run.earlier_bots),
    by_bot: { [EARLIER_BOT]: r2(run.earlier_bots) }, by_bot_realized: { [EARLIER_BOT]: r2(run.earlier_bots) },
  };
}

/** The range's holders, first-fill order, from its daily rows. */
export function byOwner(rows: ReadonlyArray<Record<Book, BookSums>>) {
  const total = (b: Book) => rows.reduce((s, r) => ({
    realized: s.realized + r[b].realized, fills: s.fills + r[b].fills,
    commissions: s.commissions + r[b].commissions, fees: s.fees + r[b].fees,
  }), NONE);
  const first = (b: Book) => rows.findIndex((r) => r[b].fills > 0);
  return BOOKS.filter((b) => first(b) >= 0)
    .sort((a, b) => first(a) - first(b) || BOOKS.indexOf(a) - BOOKS.indexOf(b))
    .map((b) => {
      const t = total(b);
      return { owner: b, bot: b === 'earlier_bots' ? EARLIER_BOT : null, ...sums(t.realized, t.fills, t.commissions, t.fees) };
    });
}

/** Each book's realized over the range, for `components`. */
export function bookComponents(rows: ReadonlyArray<Record<Book, BookSums>>) {
  const of = (b: Book) => r2(rows.reduce((s, r) => s + r[b].realized, 0));
  return {
    you_realized: of('you'), claude_realized: of('claude'), brain_realized: of('brain'),
    earlier_bots_realized: of('earlier_bots'),
    bot_realized: r2(of('claude') + of('brain') + of('earlier_bots')),
  };
}

const day = (day_pnl: number, realized_today: number, unrealized_pnl: number, fills_today: number, commissions_today: number) =>
  ({ day_pnl: r2(day_pnl), realized_today: r2(realized_today), unrealized_pnl: r2(unrealized_pnl), fills_today, commissions_today: r2(commissions_today) });

/** `books` of /api/practice/account: today's fills by book, and your open position's P&L on your book. */
export function accountBooks(fills: readonly BookFill[], yourOpenPnl: number) {
  const today = fillBooks(fills);
  const of = (b: Book, open = 0) => day(today[b].realized + open, today[b].realized, open, today[b].fills, today[b].commissions);
  const trader = (b: 'claude' | 'brain') => ({ ...of(b), budget_usd: TRADER_BUDGET_USD, budget_used_usd: 0 });
  return {
    you: of('you', yourOpenPnl),
    claude: trader('claude'),
    brain: trader('brain'),
    earlier_bots: { ...of('earlier_bots'), by_bot: today.earlier_bots.fills ? { [EARLIER_BOT]: of('earlier_bots') } : {} },
  };
}

/** Sim's scratch account before anything traded: four empty books. */
export function emptyBooks() {
  return accountBooks([], 0);
}
