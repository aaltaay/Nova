/**
 * Your book and the bots' book on the Account page (ADR 069). Mirrors backend/constants_owners.py where the
 * page needs a value; the wire is architecture/schema/recording-and-replay.md ("Your book and the bots' book").
 */
import { formatMoney } from '../utils/formatMoney';

/** Which trades the page shows: everyone's, yours, or the bots' (one bot when `bot` is set). */
export type OwnerBook = 'all' | 'you' | 'bots';

export const OWNER_BOOKS: readonly OwnerBook[] = ['all', 'you', 'bots'];
export const OWNER_SWITCH_LABELS: Record<OwnerBook, string> = { all: 'All', you: 'You', bots: 'Bots' };
export const OWNER_SWITCH_ARIA = 'Whose trades the page shows';
export const OWNER_ALL_BOTS = 'All bots';
/** The switch on Live: there is only your book there. */
export const OWNER_LIVE_WHY = 'Live: every trade is yours -- a bot never trades Live';

/** The wire's `bot` (the order's origin) in the Bots page's words. */
export const OWNER_BOT_NAMES: Record<string, string> = {
  bot: 'Strategy bot',
  auto_entry: 'Auto-entry',
  bot_api: 'Bot API',
  live_trader: 'Live Trader',
  claude: 'Claude',
};
/** A Bots menu pick's closed trades on Reports (mockup reports-v1 item 1). */
export const ownerTradeCount = (n: number): string => `${n.toLocaleString('en-US')} trade${n === 1 ? '' : 's'}`;
/** Auto-entry hands you its exit, so its shares sit on your rows (backend `YOURS_TO_SELL`). */
export const OWNER_AUTO_ENTRY = 'auto_entry';
export const OWNER_YOU_NAME = 'You';
export const OWNER_NOVA_NAME = 'Nova';
export const ownerBotName = (bot: string | null | undefined): string =>
  (bot && OWNER_BOT_NAMES[bot]) || OWNER_BOT_NAMES.bot;

export const OWNER_BOOK_YOU = 'Your book';
export const OWNER_BOOK_BOTS = "Bots' book";
export const OWNER_TODAY = 'today';
export const OWNER_MONTH = 'month';
export const OWNER_BUDGET_LABEL = "Bots' budget";
export const ownerBudgetHeld = (used: number, budget: number): string =>
  `${formatMoney(used)} of ${formatMoney(budget)} held`;
export const OWNER_BUDGET_NOTE = 'Every bot together: open positions and working entries.';

export const OWNER_WHOSE_COL = 'Whose';
export const OWNER_WHOSE_COL_TITLE = 'Whose shares: You, or the bot that holds them · Drag headers to reorder';
export const OWNER_CLOSE_BOTS = 'Close';
const shares = (qty: number): string => Math.abs(qty).toLocaleString('en-US');
/** A short (`qty` below zero) is bought back, never sold (ADR 069 decision 4). */
export const ownerCloseBotsTitle = (symbol: string, qty: number): string =>
  qty < 0
    ? `Buy back every bot's ${symbol} short -- ${shares(qty)} shares in all -- at market. Your shares stay.`
    : `Sell every bot's ${symbol} -- ${shares(qty)} shares in all -- at market. Your shares stay.`;
export const OWNER_CLOSE_BOTS_OFF_PAPER = "The bots' shares are closed on Paper";
export const OWNER_CLOSE_BOTS_SENDING = '…';
/** Close asks once more before it sends; the question stands this long. */
export const OWNER_CLOSE_BOTS_ARM_MS = 3000;
export const ownerCloseBotsConfirm = (qty: number): string =>
  qty < 0 ? `Buy back all ${shares(qty)}?` : `Sell all ${shares(qty)}?`;
export const OWNER_CLOSE_BOTS_PATH = '/api/owners/close-bots';
/** Follows a refusal: your order sent nothing, and this says where the shares are (ADR 069 decision 9). */
export const ownerBotsHoldSentence = (qty: number): string =>
  qty < 0
    ? ` The ${shares(qty)} short is the bots' -- Close on their row buys it back.`
    : ` The ${shares(qty)} shares are the bots' -- Close on their row sells them.`;
/** Under a positions list while the read of the bots' shares fails. */
export const OWNER_BOTS_UNREAD = "The bots' shares could not be read: they may be missing here.";

/** The Performance panel's P&L by day (mockup v1, approved 2026-11-03). */
export const OWNER_DAY_TAB = 'By day';
export const OWNER_DAY_LEGEND_ALL = 'All (the calendar)';
export const OWNER_DAY_EMPTY = 'No fills in this range';
