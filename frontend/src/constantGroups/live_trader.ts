/**
 * The Live Trader bot's panel on the TraderTV LIVE page (ADR 055, mockup v1 approved 2026-10-14): its words and
 * tunables.
 * Mirrors backend/bot/live_trader/constants_live_trader.py (the defaults are the operator's answers of 2026-10-14;
 * the backend's view also sends its own `defaults` and `bounds`, which win).
 */
export const LT_PATH = '/bot/live-traders';
export const LT_ASKS_PATH = '/bot/live-traders/asks';
/** The cards' poll while the TraderTV LIVE page is open; the asks' toasts poll every window, less often. */
export const LT_POLL_MS = 2_500;
export const LT_ASKS_POLL_MS = 3_000;
export const LT_ANCHOR = 'bots-live-traders';

export const LT_TITLE = 'Live Traders · TraderTV';
export const LT_SUB = 'Copies each host\'s bar on Paper. Large caps and ETFs. Never Live.';
export const LT_SUB_TIP =
  'One bot per host on the TraderTV bar. With its key on and the Bot switch on, it copies the host on Paper: a step '
  + 'when a position appears, another when their average moves (up to the adds you allow), and it sells or covers '
  + 'everything when the position leaves their bar, when they go off air, when the bar is hidden 10 minutes, and at '
  + 'the sell-all time. It skips, and says why, when the feed reads behind the stream, a ticker may be misread, their '
  + 'average is more than 1.5% from the market, a stock is not a large cap ($10B and up; an ETF always passes), or a '
  + 'step would pass the allowance.';
export const LT_PAPER_CHIP = 'Paper';
export const LT_LOADING = 'Reading the Live Trader bot…';
export const LT_FEED_OFF = 'No TraderTV feed is set up on this desk (NOVA_FOLLOW_FEED_URL), so there is no host to copy.';
export const LT_NO_HOSTS = 'No host has been read on the TraderTV bar today yet.';
/** A blocker whose control is on the Bots page (the Bot switch, Freeze all orders) links there. The daily loss limit's
 * (`LT_LOSS_LIMIT`, ADR 056) lives in Settings > Loss limits, and its words say so. */
export const LT_BOTS_PAGE_CODES: readonly string[] = ['LT_BOT_OFF', 'LT_FROZEN'];
export const LT_OPEN_BOTS = 'Open the Bots page';
export const LT_OPEN_BOTS_TIP = 'The Bot switch and Freeze all orders are on the Bots page.';

export const LT_KEY_LABEL = 'Bot key';
export const LT_KEY_TIP_ON = 'On: this host\'s bot copies them on Paper while the Bot switch is on. Click to turn it off.';
export const LT_KEY_TIP_OFF = 'Off: this host\'s bot does nothing. Click to turn it on.';
export const LT_ENTRY_LABEL = 'Entry';
export const LT_EXIT_LABEL = 'Exit';
export const LT_ALLOWANCE_LABEL = 'Allowance';
export const LT_TODAY_LABEL = 'Today';
export const LT_TRADES_LABEL = 'Trades';
export const LT_SKIPPED_LABEL = 'Skipped';
export const LT_NO_POSITIONS = 'No positions held.';
export const LT_CHANGE = 'Change';
export const LT_DONE = 'Done';
export const LT_APPROVE = 'Approve';
export const LT_SKIP = 'Skip';
export const LT_EVENTS_SHOWN = 4;
/** Why a control is locked (ux/whyTip.ts): every control works or says why not. */
export const LT_BUSY_WHY = 'Saving your change…';
export const LT_ANSWERED_WHY = 'Answered: the bot checks every rule again before it sends anything';

/** Turning a key, or the Bot switch, off while the bot holds positions asks first (operator, 2026-10-14). */
export const ltKeyOffTitle = (name: string): string => `Turn ${name}'s bot off?`;
export const LT_BOT_OFF_TITLE = 'Turn the bot off?';
export const ltHeldList = (held: { symbol: string; qty: number; side: string }[]): string =>
  held.map(h => `${h.symbol} ${h.qty} ${h.qty === 1 ? 'share' : 'shares'}${h.side === 'short' ? ' short' : ''}`).join(', ');
export const ltKeyOffMessage = (held: { symbol: string; qty: number; side: string }[]): string =>
  `It holds ${held.length} position${held.length === 1 ? '' : 's'} on Paper: ${ltHeldList(held)}. `
  + 'Turning it off sells them now.';
export const ltBotOffMessage = (held: { symbol: string; qty: number; side: string }[]): string =>
  `The Live Trader bot holds ${held.length} position${held.length === 1 ? '' : 's'} on Paper: ${ltHeldList(held)}. `
  + 'Turning the bot off sells them now.';
export const ltSellAndOff = (n: number): string => `Sell ${n} and turn off`;
export const LT_KEEP_ON = 'Keep it on';

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
