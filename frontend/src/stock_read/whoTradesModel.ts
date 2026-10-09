/**
 * Who trades the stock on the desk (ADR 037), pure: the four modes in words, why a side of the switch
 * is locked, and the plan's levels with what stands behind each -- drawn dashed on the charts while only a
 * plan, solid while an order stands there, and as ENTRY / STOP / TARGET rows in the Level 2 book. The plan
 * card's buttons for the mode are `planActions.ts`.
 */
import type { DepthMarker } from '../ibkr';
import { SETUP_COLORS } from './constants';
import { judgedLevels, type MomentInputs } from './momentModel';
import { heldAnyQty } from './momentShort';
import { fmtPx } from './planMath';
import { thinPlan } from './planVerdict';
import type { StockModeName, StockModeTrade, StockModeView, StockSide } from './types';

export const MODE_NAMES: Record<StockModeName, string> = {
  signal: 'Signal only',
  approve: 'Approve',
  auto_entry: 'Auto-entry',
  bot: 'Bot',
};

/** Entry · Exit (ADR 048): who enters and who exits; the strategy that triggers decides long or short. */
export const MODE_SIDES: Record<StockModeName, string> = {
  signal: 'you enter · you exit',
  approve: 'you approve · bot exits',
  auto_entry: 'bot enters · you exit',
  bot: 'bot enters · bot exits',
};

export const MODE_ORDER: readonly StockModeName[] = ['signal', 'approve', 'auto_entry', 'bot'];

/** What the mode means, in the plan card's words. Auto-entry follows the bot's rules with the exit handed
 * to you (ADR 042 draft): a go trigger of a setup at Strategy, while the bot is active, within the day's
 * shared cap. */
export function modeSentence(mode: StockModeName, symbol: string): string {
  switch (mode) {
    case 'approve':
      return 'You approve once. Nova sends the entry with its stop and target.';
    case 'auto_entry':
      return `The bot enters ${symbol} at a go trigger of a strategy at On, by the bot's rules, while the bot is `
        + 'on: the strategy decides long or short. Every exit is yours.';
    case 'bot':
      return `The bot enters ${symbol} at a go trigger of a strategy at On while it is active (the strategy decides `
        + 'long or short), and exits at the target, the stop or after 15 minutes.';
    default:
      return 'Nova draws the plan and tells you when. It places nothing.';
  }
}

export function sidesOf(mode: StockModeName): { buy: StockSide; sell: StockSide } {
  return {
    buy: mode === 'auto_entry' || mode === 'bot' ? 'nova' : 'you',
    sell: mode === 'approve' || mode === 'bot' ? 'nova' : 'you',
  };
}

export function modeOf(buy: StockSide, sell: StockSide): StockModeName {
  if (buy === 'nova') return sell === 'nova' ? 'bot' : 'auto_entry';
  return sell === 'nova' ? 'approve' : 'signal';
}

/** Why the switch cannot move to `to` now; null: it can. `pending` is the desk's own reason to wait. */
/** Why Nova does not take the exit of a held stock on Live (the backend's `STOCK_MODE_WHY_LIVE_EXIT`). */
export const HELD_LIVE_EXIT_WHY = 'On Live, Nova never moves a Live order by itself, and a plain IBKR stop does not '
  + 'trigger before 9:30 (#604). Set your stop and sell it yourself; Nova takes the exit on Paper and Sim.';
/** The same for a short you hold (ADR 048): Nova takes the cover on Paper and Sim only. */
export const HELD_LIVE_COVER_WHY = 'On Live, Nova never moves a Live order by itself (#604). Keep your buy stop and '
  + 'cover it yourself; Nova takes the cover on Paper and Sim.';

export function switchLock(
  view: StockModeView | null,
  to: { buy: StockSide; sell: StockSide },
  o: { symbol: string; held: number; pending: string | null; short?: boolean },
): string | null {
  if (o.pending) return o.pending;
  if (!view) return `Reading who trades ${o.symbol}…`;
  const mode = modeOf(to.buy, to.sell);
  const byMode = mode === 'signal' ? undefined : view.locks.modes?.[mode];
  if (byMode) return byMode;                  // e.g. on a Sim replay only Bot is Nova's (ADR 052)
  if (to.buy === 'nova' && view.locks.buy) return view.locks.buy;
  if (to.sell === 'nova' && view.locks.sell) {
    return o.held > 0 ? (o.short ? HELD_LIVE_COVER_WHY : HELD_LIVE_EXIT_WHY) : view.locks.sell;
  }
  // Sell to Nova on a stock you hold opens "Nova takes the exit" (the row's own handler): no lock here.
  return null;
}

// -- the plan's levels and what stands behind them ------------------------------------------------
export type Behind = 'plan' | 'order' | 'held' | 'watched';

export interface OrderLevel {
  price: number;
  behind: Behind;
}

export interface OrderLevels {
  entry: OrderLevel | null;
  stop: OrderLevel | null;
  target: OrderLevel | null;
}

function level(price: number | null, behind: Behind): OrderLevel | null {
  return price !== null && Number.isFinite(price) ? { price, behind } : null;
}

/** Nova's trade on the stock while it is entering or held; null otherwise. */
export function liveTrade(who: StockModeView | null): StockModeTrade | null {
  const t = who?.trade ?? null;
  return t && (t.state === 'entering' || t.state === 'holding') ? t : null;
}

/** The levels the charts and Level 2 draw: Nova's live trade's own, the levels a held position is judged
 * by, else the plan's. */
export function orderLevels(i: MomentInputs): OrderLevels | null {
  const live = liveTrade(i.who);
  if (live) {
    const holding = live.state === 'holding';
    // Nova's exits: the bracket's two legs are orders from the send (the bot's entry is a bracket too,
    // spec I); a bot trade without a stop order watches its stop. Once the operator takes the exit over,
    // both are only the plan again.
    const nova = live.exits === 'nova';
    const bot = live.kind === 'bot';
    const botStop: Behind = live.stop_order_id !== null ? 'order' : holding ? 'watched' : 'plan';
    return {
      entry: level(live.fill_price ?? live.entry, holding ? 'held' : 'order'),
      stop: level(live.stop, !nova ? 'plan' : bot ? botStop : 'order'),
      target: level(live.target, !nova ? 'plan' : bot ? (live.target_order_id !== null ? 'order' : 'plan') : 'order'),
    };
  }
  const plan = i.read?.plan ?? null;
  if (heldAnyQty(i) > 0) {
    // The chart draws the position's own cost; the plan's entry turns solid once shares are held (long or short).
    const lv = judgedLevels(i);
    return {
      entry: level(lv?.entry ?? null, 'held'),
      stop: level(lv?.stop ?? null, 'plan'),
      target: level(lv?.target ?? null, 'plan'),
    };
  }
  // A setup plan too thin to trade is no plan (2026-10-01): nothing drawn, nothing marked in Level 2.
  if (!plan || thinPlan(plan)) return null;
  return { entry: level(plan.entry, 'plan'), stop: level(plan.stop, 'plan'), target: level(plan.target, 'plan') };
}

const TIPS: Record<'entry' | 'stop' | 'target', Partial<Record<Behind, string>>> = {
  entry: {
    plan: "The plan's entry, a buy limit here. Only a plan: no order stands behind it.",
    order: "Nova's buy is working here.",
    held: "Shares are held: the plan's entry is in effect.",
  },
  stop: {
    plan: "The plan's stop. Only a plan: no order stands behind it.",
    order: 'A stop order stands here.',
    watched: 'The bot watches this stop and sells when it prints.',
  },
  target: {
    plan: "The plan's target. Only a plan: no order stands behind it.",
    order: 'A sell limit rests here.',
  },
};

const TIPS_SHORT: Record<'entry' | 'stop' | 'target', Partial<Record<Behind, string>>> = {
  entry: {
    plan: "The plan's short entry, a sell limit here that goes out with its buy stop. Only a plan: no order stands behind it.",
    order: 'A short entry is working here.',
    held: 'Shares are held short: the plan\'s entry is in effect.',
  },
  stop: {
    plan: "The plan's buy stop over the entry. Only a plan: no order stands behind it.",
    order: 'A buy stop order stands here.',
    watched: 'The bot watches this buy stop and covers when it prints.',
  },
  target: {
    plan: "The plan's cover target. Only a plan: no order stands behind it.",
    order: 'A buy limit (the cover) rests here.',
  },
};

/** ENTRY / STOP / TARGET for the Level 2 book; a short plan's SHORT, STOP ↑ and TARGET ↓ (ADR 048): its entry
 * sells and its buy stop sits over the price with the asks, its cover target under it with the bids. */
export function level2Markers(levels: OrderLevels | null, side: 'long' | 'short' = 'long'): DepthMarker[] {
  if (!levels) return [];
  const short = side === 'short';
  const words = short ? { entry: 'SHORT', stop: 'STOP ↑', target: 'TARGET ↓' } : { entry: 'ENTRY', stop: 'STOP', target: 'TARGET' };
  const tips = short ? TIPS_SHORT : TIPS;
  const out: DepthMarker[] = [];
  const add = (id: 'entry' | 'stop' | 'target', lv: OrderLevel | null, color: string, rests: 'bid' | 'ask') => {
    if (!lv) return;
    out.push({
      id,
      price: lv.price,
      label: `${words[id]} ${fmtPx(lv.price)}`,
      color,
      working: lv.behind !== 'plan',
      rests,
      tip: tips[id][lv.behind] ?? '',
    });
  };
  add('entry', levels.entry, SETUP_COLORS.trigger, short ? 'ask' : 'bid');
  add('stop', levels.stop, SETUP_COLORS.stop, short ? 'ask' : 'bid');
  add('target', levels.target, SETUP_COLORS.target, short ? 'bid' : 'ask');
  return out;
}

/** A price line's title for the level and what stands behind it; a short's SHORT, STOP ↑ and TARGET ↓ (ADR 048). */
export function levelTitle(id: 'entry' | 'stop' | 'target', behind: Behind, targetR = '', short = false): string {
  const entry = short ? 'SHORT' : 'ENTRY';
  const stop = short ? 'STOP ↑' : 'STOP';
  const target = short ? 'TARGET ↓' : 'TARGET';
  if (id === 'entry') return behind === 'held' ? `${entry} · held` : behind === 'order' ? `${entry} · working` : entry;
  if (id === 'stop') return behind === 'order' ? `${stop} · order` : behind === 'watched' ? `${stop} · Nova watches` : `${stop} · plan`;
  return behind === 'order' ? `${target} · order` : `${target}${targetR} · plan`;
}
