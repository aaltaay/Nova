/**
 * The Live Trader bots on Bots > LiveTrader Bots (ADR 055; approved from a render 2026-10-15): each host's bot in the
 * middle of their card, the LiveTrader Bots key's line in the page's head. Their words and tunables.
 * Mirrors backend/bot/live_trader/constants_live_trader.py (the defaults are the operator's answers of 2026-10-14;
 * the backend's view also sends its own `defaults` and `bounds`, which win).
 */
export const LT_PATH = '/bot/live-traders';
export const LT_ASKS_PATH = '/bot/live-traders/asks';
/** The cards' poll while LiveTrader Bots is open; the asks' toasts poll every window, less often. */
export const LT_POLL_MS = 2_500;
export const LT_ASKS_POLL_MS = 3_000;

export const LT_LOADING = 'Reading the Live Trader bots…';
/** The head's one line while the hosts' bots cannot trade: these words, then the reason's first clause. */
export const LT_NO_ORDERS = 'No orders';
/** A blocker whose control is on another page links there: Freeze all orders is on Strategy Bots. The Bot switch is
 * in the header and the LiveTrader Bots key beside the line, and their words say so (2026-10-15); the daily loss
 * limit's (`LT_LOSS_LIMIT`, ADR 056) lives in Settings > Loss limits, and its words say so. */
export const LT_BOTS_PAGE_CODES: readonly string[] = ['LT_FROZEN'];
export const LT_OPEN_BOTS = 'Open Strategy Bots';
export const LT_OPEN_BOTS_TIP = 'Freeze all orders is on Strategy Bots, in the Bot card.';

export const LT_KEY_LABEL = 'Bot';
export const LT_KEY_TITLE = 'Bot key';
export const LT_KEY_TIP_ON =
  'On: this host’s bot copies them on Paper while the Bot switch and the LiveTrader Bots key are on. Click to turn '
  + 'it off: it then places no order, not even a sell.';
export const LT_KEY_TIP_OFF = 'Off: this host’s bot places no order, not even a sell. Click to turn it on.';
export const LT_ENTRY_LABEL = 'Entry';
export const LT_EXIT_LABEL = 'Exit';
export const LT_ALLOWANCE_LABEL = 'Allowance';
export const LT_TODAY_LABEL = 'Today';
export const LT_RULES = 'Rules';
export const LT_RULES_CLICK = 'Click to change them.';
export const LT_PAPER_ONLY = 'Paper only, never Live';
export const LT_DONE = 'Done';
export const LT_APPROVE = 'Approve';
export const LT_SKIP = 'Skip';
export const LT_APPROVED = 'approved';
export const ltBotOf = (name: string): string => `${name}'s bot`;
export const ltTrades = (n: number): string => `${n} trade${n === 1 ? '' : 's'}`;
export const ltSkipped = (n: number): string => `${n} skipped`;
export const ltSkipsTitle = (name: string, n: number): string => `${name}'s bot · ${n} skipped today`;
export const ltNewestOf = (shown: number, total: number): string => `the newest ${shown} of ${total}`;
export const ltBadge = (qty: number): string => `BOT ${qty} sh`;
export const ltMoreAsks = (n: number): string => `+${n} more`;
export const ltSecondsLeft = (n: number): string => `${n} s left`;
/** Why a control is locked (ux/whyTip.ts): every control works or says why not. */
export const LT_BUSY_WHY = 'Saving your change…';
export const LT_ANSWERED_WHY = 'Answered: the bot checks every rule again before it sends anything';

/* Turning a key or the Bot switch off sells nothing, so nothing asks first (operator decision 2026-10-15). */

/** The settings' editors (bounds from the backend's view when it sends them). */
export const LT_ADDS_CHOICES: readonly (number | null)[] = [0, 2, 4, null];
export const ltAddsWords = (n: number | null): string => (n === null ? 'every add' : n === 0 ? 'no adds' : `${n} adds`);
export const LT_SIDES_WORDS: Record<string, string> = { long: 'Longs only', both: 'Longs and shorts' };
export const LT_TAKE_OPEN_WORDS = { take: 'Takes already open', skip: 'Skips already open' };
export const ltStepWords = (usd: number): string => `$${usd.toLocaleString('en-US')} a step`;
export const ltAllowanceWords = (usd: number): string => `$${usd.toLocaleString('en-US')} allowance`;
export const ltShortStopWords = (pct: number): string => `${pct}% buy stop`;
export const ltSellAllWords = (hhmm: string): string => `Sells all at ${hhmm}`;
export const LT_LARGE_CAPS = 'Large caps ($10B+) and ETFs';
