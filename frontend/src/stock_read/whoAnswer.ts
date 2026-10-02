/**
 * The stock's own answer in its Who trades row (ADR 044): "Nova may buy AISP: no · the bot is off".
 * The same question the Bots page answers for every ticker, for this one: listed today, Buy on Nova,
 * and nothing the backend names in the switch's notes (ADR 042's every-blocker list).
 */
import type { StockModeView } from './types';

export interface WhoAnswer {
  tone: 'yes' | 'no' | 'you';
  text: string;
}

export function whoAnswer(sym: string, listed: boolean | null, view: StockModeView | null): WhoAnswer | null {
  if (!view) return null;
  if (listed === false) return { tone: 'no', text: `Nova may buy ${sym}: no · not on today's hot list` };
  if (view.buy !== 'nova') return { tone: 'you', text: `Nova may buy ${sym}: no · you buy it` };
  const warns = (view.notes ?? []).filter(n => n.tone === 'warn');
  if (warns.length) {
    const more = warns.length > 1 ? ` (and ${warns.length - 1} more below)` : '';
    return { tone: 'no', text: `Nova may buy ${sym}: no · ${warns[0].text}${more}` };
  }
  if (listed === null) return null;
  return { tone: 'yes', text: `Nova may buy ${sym}: yes, at its next go trigger` };
}
