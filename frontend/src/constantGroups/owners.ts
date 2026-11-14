/**
 * The three traders' books (ADR 072): you, Claude and the brain, plus read-only Earlier bots (what the retired bots
 * held and traded). Mirrors backend/constants_owners.py where the desk needs a value; the wire is
 * architecture/schema/recording-and-replay.md ("Three traders' books") and architecture/schema/traders.md.
 * Approved screens: F:\Nova\design\three-books\v1.
 */
import { formatMoney } from '../utils/formatMoney';

/** A book on the wire (`owner`): one of the three traders, or the retired bots' history. */
export type Owner = 'you' | 'claude' | 'brain' | 'earlier_bots';
/** The AI traders, each with an On / Off switch and a budget. */
export type AiTrader = 'claude' | 'brain';
/** Which trades the page shows: everyone's, or one book's (one retired bot when `bot` is set). */
export type OwnerBook = 'all' | Owner;

/** Every book, in the order every split reads them. */
export const OWNERS: readonly Owner[] = ['you', 'claude', 'brain', 'earlier_bots'];
export const AI_TRADERS: readonly AiTrader[] = ['claude', 'brain'];
export const OWNER_BOOKS: readonly OwnerBook[] = ['all', ...OWNERS];
export const OWNER_SWITCH_LABELS: Record<OwnerBook, string> = {
  all: 'All', you: 'You', claude: 'Claude', brain: 'The brain', earlier_bots: 'Earlier bots',
};
/** The phone's one row of five (mockup three-books v1, phone a). */
export const OWNER_SHORT_LABELS: Record<OwnerBook, string> = {
  all: 'All', you: 'You', claude: 'Claude', brain: 'Brain', earlier_bots: 'Earlier',
};
/** Each book in Nova's words, mid-sentence ("the brain"). */
export const OWNER_NAMES: Record<Owner, string> = {
  you: 'You', claude: 'Claude', brain: 'The brain', earlier_bots: 'Earlier bots',
};
/** Each book's colour (mockup v1 section 7): you cyan, Claude coral, the brain purple, Earlier bots grey. */
export const OWNER_COLORS: Record<Owner, string> = {
  you: '#64d2ff', claude: '#d97757', brain: '#8b5cf6', earlier_bots: '#8e8e93',
};
export const OWNER_SWITCH_ARIA = 'Whose trades the page shows';
export const OWNER_ALL_BOTS = 'All earlier bots';
/** The switch on Live: there is only your book there. */
export const OWNER_LIVE_WHY = 'Live: every trade is yours -- Claude and the brain never trade Live';

/** A retired bot (the wire's `bot`, its origin) in Nova's words. */
export const OWNER_BOT_NAMES: Record<string, string> = {
  bot: 'Strategy bot',
  auto_entry: 'Auto-entry',
  bot_api: 'Bot API',
  live_trader: 'Live Trader',
};
/** A pick's closed trades on Reports (mockup reports-v1 item 1). */
export const ownerTradeCount = (n: number): string => `${n.toLocaleString('en-US')} trade${n === 1 ? '' : 's'}`;
export const OWNER_YOU_NAME = 'You';
export const OWNER_NOVA_NAME = 'Nova';
export const ownerBotName = (bot: string | null | undefined): string =>
  (bot && OWNER_BOT_NAMES[bot]) || OWNER_BOT_NAMES.bot;
/** True for a book with no switch and no new orders: the retired bots' history. */
export const isEarlier = (owner: string | null | undefined): boolean => owner === 'earlier_bots';

export const OWNER_TODAY = 'today';
export const OWNER_MONTH = 'month';
export const OWNER_THREE_BOOKS = 'Three books, one account';
export const OWNER_EARLIER_HISTORY = 'history only';
export const OWNER_NO_TRADES_YET = 'no trades yet';
export const OWNER_BUDGETS = "Each trader's own budget";
export const ownerBudgetLabel = (trader: AiTrader): string => `${OWNER_NAMES[trader]}'s budget`;
export const ownerBudgetHeld = (used: number, budget: number): string =>
  `${formatMoney(used)} of ${formatMoney(budget)} held`;
export const OWNER_BUDGET_NOTE = 'Open positions at the mark plus working entries.';

export const OWNER_WHOSE_COL = 'Whose';
export const OWNER_WHOSE_COL_TITLE = 'Whose shares: You, Claude, the brain, or a retired bot · Drag headers to reorder';
/** A trade you closed after its trader handed it to you: its P&L stays on that trader's record. */
export const ownerClosedByYou = (owner: Owner): string => `${OWNER_NAMES[owner]} · closed by you`;
/** A switched-off trader's open position, yours to close. */
export const ownerYoursToClose = (owner: Owner): string =>
  owner === 'earlier_bots' ? 'A retired bot\'s · yours to close' : `${OWNER_NAMES[owner]}'s · yours to close`;
export const OWNER_HANDED = 'Handed';
const shares = (qty: number): string => Math.abs(qty).toLocaleString('en-US');
/** Follows a refusal: your order sent nothing, and this says whose the shares are (ADR 072). */
export const ownerHoldSentence = (owner: Owner, qty: number): string => {
  const what = `The ${shares(qty)} ${qty < 0 ? 'short is' : 'shares are'}`;
  if (owner === 'earlier_bots') return ` ${what} a retired bot's.`;
  const name = owner === 'brain' ? 'the brain' : OWNER_NAMES[owner];
  return ` ${what} ${name}'s -- switch ${name} off to close ${qty < 0 ? 'it' : 'them'} yourself.`;
};
/** Under a positions list while the read of the other traders' shares fails. */
export const OWNER_OTHERS_UNREAD = "The other traders' shares could not be read: they may be missing here.";

/** The Performance panel's P&L by day (mockup v1, approved 2026-11-03). */
export const OWNER_DAY_TAB = 'By day';
export const OWNER_DAY_LEGEND_ALL = 'All (the calendar)';
export const OWNER_DAY_EMPTY = 'No fills in this range';
/** The calendar day card's rows (mockup three-books v1 section 5). */
export const OWNER_BY_TRADER = 'By trader';
