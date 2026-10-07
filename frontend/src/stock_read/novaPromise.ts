/**
 * Whether Nova will trade this stock by itself, and with what size (ADR 042 draft, spec F), long or short (ADR 049).
 * Pure. The chart's call promises a Nova trade ("THE BOT TRADES THIS", "BOT BUYS AT ...", "BOT SHORTS AT ...") only
 * when nothing stands in the way,
 * and otherwise says why -- every reason, in order: the view's blocking notes, then what the bot's own fields
 * say (the plan's setup not at Strategy, the bot not active or not playing), then the day's shared cap of
 * Nova's automatic trades, both sides counted. The size is the backend's own (`size`), never estimated here.
 */
import { setupName, sizeFor } from './planMath';
import type { StockModeSize, StockModeView, StockPlan } from './types';

/** A note's id that already says what a bot field says: the field adds no second sentence. */
const SAYS_STRATEGY = new Set(['not_strategy']);
const SAYS_ACTIVE = new Set(['not_active']);
const SAYS_PLAYING = new Set(['bot_not_playing', 'not_playing']);
const SAYS_CAP = new Set(['daily_cap', 'entry_used']);

const OLDER = 'This backend does not say whether the bot will trade it: reload the backend.';

function plural(n: number, one: string, many: string): string {
  return n === 1 ? one : many;
}

/** The day's shared cap of Nova's automatic trades (longs and shorts) is used: in words; null while one is left or
 * unknown. */
export function capUsedText(who: StockModeView | null): string | null {
  const e = who?.entries_today ?? null;
  if (!e || e.cap === null || e.count < e.cap) return null;
  const venue = who?.venue ? ` on ${who.venue === 'sim' ? 'Sim' : who.venue === 'live' ? 'Live' : 'Paper'}` : '';
  const trades = plural(e.cap, 'automatic trade', `${e.cap} automatic trades`);
  return `Nova's ${e.cap === 1 ? 'one ' : ''}${trades}${venue} today ${plural(e.cap, 'is', 'are')} used `
    + `(${e.count} of ${e.cap}): the bot and Auto-entry trade again on the next day.`;
}

/**
 * Every reason Nova will not trade this stock by itself now, first to last; empty when nothing stands in the
 * way, or the stock is not in a mode where Nova enters (Signal only, Approve: the operator decides).
 */
export function novaBlockers(who: StockModeView | null, plan: StockPlan | null): string[] {
  if (!who || (who.mode !== 'bot' && who.mode !== 'auto_entry')) return [];
  const out: string[] = [];
  const ids = new Set<string>();
  const cap = capUsedText(who);
  if (cap) out.push(cap);
  for (const n of who.notes) {
    if (n.tone === 'info' || out.includes(n.text)) continue;
    if (cap && SAYS_CAP.has(n.id)) continue;                  // the cap's own sentence leads already
    out.push(n.text);
    ids.add(n.id);
  }
  const has = (set: Set<string>) => [...set].some(id => ids.has(id));
  const setup = plan?.source === 'setup' ? `the ${setupName(plan.setup_type).toLowerCase()}` : 'the plan\'s setup';
  const bot = who.bot;
  if (who.mode === 'bot') {
    if (!bot) return out.length ? out : [OLDER];
    if (bot.setup_at_strategy !== true && !has(SAYS_STRATEGY)) {
      out.push(bot.setup_at_strategy === false
        ? `${capital(setup)} is not at Strategy: the bot trades only setups at Strategy.`
        : `The desk cannot tell whether ${setup} is at Strategy, so it promises no bot trade.`);
    }
    if (bot.active !== true && !has(SAYS_ACTIVE)) {
      out.push(bot.active === false ? 'The bot is not active: press Activate on the Bots page.' : OLDER);
    }
    if (!bot.playing && !has(SAYS_PLAYING) && out.length === 0) {
      out.push(`The bot is not playing: ${bot.reason ?? 'it gave no reason'}.`);
    }
  } else if (bot) {
    // Auto-entry follows the bot's rules: a setup at Strategy, and only while the bot is active.
    if (bot.setup_at_strategy === false && !has(SAYS_STRATEGY)) {
      out.push(`${capital(setup)} is not at Strategy: Auto-entry enters only a setup at Strategy.`);
    }
    if (bot.active === false && !has(SAYS_ACTIVE)) {
      out.push('The bot is not active: Auto-entry enters only while it is. Press Activate on the Bots page.');
    }
  }
  return [...new Set(out)];
}

function capital(s: string): string {
  return s ? `${s[0].toUpperCase()}${s.slice(1)}` : s;
}

/** Nova's own size for the stock's plan: whole shares, or null when the view says none (or no size). */
export function novaQty(who: StockModeView | null): number | null {
  const q = who?.size?.qty ?? null;
  return q !== null && q >= 1 ? Math.floor(q) : null;
}

/** What Approve sends: Nova's size for the plan when the view gives one, else the risk per trade over the
 * plan's risk a share. */
export function approveQty(who: StockModeView | null, riskUsd: number, plan: StockPlan | null): number | null {
  if (who?.size) return novaQty(who);
  return plan ? sizeFor(riskUsd, plan.risk) : null;
}

const CAP_WORDS: Record<NonNullable<StockModeSize['capped_by']>, string> = {
  max_shares: 'the sleeve\'s max shares',
  budget: 'the sleeve\'s budget',
};

/** "Nova sends 10 (200 by risk, capped by the sleeve's max shares)", or the stated skip. */
export function novaSizeWords(size: StockModeSize | null): { text: string; tip: string; skip: boolean } | null {
  if (!size) return null;
  if (size.qty < 1) {
    return { text: `Nova sends nothing: ${size.text ?? 'the risk per trade buys no whole share'}`,
      tip: size.text ?? 'The risk per trade buys no whole share at this risk a share, so Nova skips it.', skip: true };
  }
  const qty = Math.floor(size.qty).toLocaleString('en-US');
  const byRisk = size.by_risk !== null ? `${Math.floor(size.by_risk).toLocaleString('en-US')} by risk` : 'by risk';
  const why = size.capped_by ? ` (${byRisk}, capped by ${CAP_WORDS[size.capped_by]})` : ` (${byRisk})`;
  return {
    text: `Nova sends ${qty}${why}`,
    tip: size.text ?? 'The sleeve\'s risk per trade over the plan\'s risk a share, capped by the sleeve\'s max shares '
      + 'and the budget left.',
    skip: false,
  };
}
