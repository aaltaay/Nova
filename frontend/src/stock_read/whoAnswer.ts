/**
 * The stock's own answer in its Who trades row (ADR 044): "Bot may buy AISP: no · the bot is off".
 * The same question the Bots page answers for every ticker, for this one: Buy on Bot, and nothing the
 * backend names in the switch's notes (ADR 042's every-blocker list). The hot list is no part of it (ADR 044,
 * amended 2026-10-06): a star is watching only.
 */
import type { StockModeView } from './types';

export interface WhoAnswer {
  tone: 'yes' | 'no' | 'you';
  text: string;
}

export function whoAnswer(sym: string, view: StockModeView | null): WhoAnswer | null {
  if (!view) return null;
  if (view.buy !== 'nova') return { tone: 'you', text: `Bot may buy ${sym}: no · you buy it` };
  const warns = (view.notes ?? []).filter(n => n.tone === 'warn');
  if (warns.length) {
    const more = warns.length > 1 ? ` (and ${warns.length - 1} more below)` : '';
    return { tone: 'no', text: `Bot may buy ${sym}: no · ${warns[0].text}${more}` };
  }
  return { tone: 'yes', text: `Bot may buy ${sym}: yes, at its next go trigger` };
}
