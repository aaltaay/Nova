/**
 * The stock's own answer in its Who trades row (ADR 044; Entry · Exit since ADR 048): "Bot may trade AISP: no ·
 * Entry is You". The same question the Bots page answers for every ticker, for this one: Entry on Bot, and nothing
 * the backend names in the switch's notes (ADR 042's every-blocker list). The hot list is no part of it (ADR 044,
 * amended 2026-10-06): a star is watching only.
 *
 * With Entry on Bot the strategy that triggers decides long or short, and a second line says what is forming
 * now. While you hold the stock short, the bot enters nothing on it (Nova never trades against you, ADR 048).
 */
import { setupName } from './planMath';
import type { StockModeView, StockPlan } from './types';

export interface WhoAnswer {
  tone: 'yes' | 'no' | 'you';
  text: string;
}

export function whoAnswer(sym: string, view: StockModeView | null, heldShort = 0): WhoAnswer | null {
  if (!view) return null;
  if (heldShort > 0) return { tone: 'no', text: `You hold ${sym} short: the bot enters nothing on ${sym} while you do` };
  if (view.buy !== 'nova') return { tone: 'you', text: `Bot may trade ${sym}: no · Entry is You` };
  const warns = (view.notes ?? []).filter(n => n.tone === 'warn');
  if (warns.length) {
    const more = warns.length > 1 ? ` (and ${warns.length - 1} more below)` : '';
    return { tone: 'no', text: `Bot may trade ${sym}: no · ${warns[0].text}${more}` };
  }
  return { tone: 'yes', text: `Bot may trade ${sym}: yes, at its next go trigger` };
}

/** With Entry on Bot: "Long or short: the strategy decides · forming now: Bull flag ▲ LONG"; null otherwise. */
export function sideLine(view: StockModeView | null, plan: StockPlan | null): string | null {
  if (!view || view.buy !== 'nova') return null;
  const forming = plan && plan.source === 'setup'
    ? `forming now: ${setupName(plan.setup_type)} ${plan.side === 'short' ? '▼ SHORT' : '▲ LONG'}`
    : 'nothing forming now';
  return `Long or short: the strategy decides · ${forming}`;
}
